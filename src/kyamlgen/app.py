"""The FastAPI application.

The server does four things: hand the browser a widget tree, turn a submitted object
back into YAML, validate it, and analyse it against the other objects in the same
bundle.
"""

from __future__ import annotations

import functools
from typing import Any

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import __version__
from .presets import curated_kinds, is_curated, preset_for
from .registry import describe
from .render import parse_yaml, to_bundle_yaml
from .schemas import (
    SchemaError,
    available_versions,
    default_version,
    kind_index,
    load_bundle,
    version_key,
)
from .semantics import analyse
from .validate import Issue, SchemaValidator, check_form
from .widgets import WidgetBuilder

BASE_DIR = __import__("pathlib").Path(__file__).parent

app = FastAPI(title="kyamlgen", version=__version__)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@functools.lru_cache(maxsize=1)
def _bundle(version: str) -> Any:
    return load_bundle(version, strict=True)


@functools.lru_cache(maxsize=1)
def _validator(version: str) -> SchemaValidator:
    return SchemaValidator(_bundle(version))


@functools.lru_cache(maxsize=256)
def _widget_tree(version: str, kind: str, api_version: str) -> dict[str, Any]:
    return WidgetBuilder(_bundle(version)).build(kind, api_version)


def _client_tree(node: dict[str, Any]) -> dict[str, Any]:
    """Strip the fields the browser has no use for.

    The tree for a Deployment is over 1300 nodes and half a megabyte of JSON, so the
    ``id`` and ``path`` fields — which the server uses internally but the renderer
    never reads — are removed before it goes to the browser.
    """
    trimmed = {key: value for key, value in node.items() if key not in ("id", "path")}
    if "children" in trimmed:
        trimmed["children"] = [_client_tree(child) for child in trimmed["children"]]
    if "item" in trimmed:
        trimmed["item"] = _client_tree(trimmed["item"])
    return trimmed


def _kinds(version: str) -> list[dict[str, Any]]:
    """Every top-level kind in the schema bundle, grouped for the picker.

    A kind available in several versions (``HorizontalPodAutoscaler`` exists as v1 and
    v2) appears once, under its newest version.  The older version is still reachable
    by asking for it explicitly.
    """
    newest: dict[tuple[str, str], Any] = {}
    for ref in kind_index(version).values():
        key = (ref.group, ref.kind)
        current = newest.get(key)
        if current is None or version_key(ref.version) > version_key(current.version):
            newest[key] = ref

    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for ref in newest.values():
        info = describe(ref)
        seen[ref.key] = {
            "apiVersion": info.api_version,
            "kind": info.kind,
            "group": info.group,
            "version": info.version,
            "plural": info.plural,
            "namespaced": info.namespaced,
            "authorable": info.authorable,
            "curated": is_curated(info.kind),
            "note": info.note,
            "category": info.tags[0] if info.tags else "Other",
        }
    return sorted(seen.values(), key=lambda item: (item["category"], item["kind"]))


class ObjectPayload(BaseModel):
    apiVersion: str
    kind: str
    manifest: dict[str, Any] = Field(default_factory=dict)


class RenderRequest(BaseModel):
    version: str | None = None
    objects: list[ObjectPayload] = Field(default_factory=list)


class ValidateRequest(BaseModel):
    version: str | None = None
    yaml: str


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Any:
    version = default_version()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "version": version,
            "versions": available_versions(),
            "kinds": _kinds(version),
            "app_version": __version__,
        },
    )


@app.get("/form", response_class=HTMLResponse)
def form(request: Request, apiVersion: str, kind: str, version: str | None = None) -> Any:
    version = version or default_version()
    api_version = apiVersion
    candidates = [item for item in _kinds(version) if item["kind"] == kind]
    if not candidates:
        return HTMLResponse(f"Unknown kind '{kind}' for Kubernetes {version}.", status_code=404)
    if not any(item["apiVersion"] == apiVersion for item in candidates):
        api_version = candidates[0]["apiVersion"]

    tree = _widget_tree(version, kind, api_version)
    info = next((item for item in candidates if item["apiVersion"] == api_version), candidates[0])
    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "version": version,
            "api_version": api_version,
            "kind": kind,
            "tree": _client_tree(tree),
            "preset": preset_for(kind),
            "info": {
                "plural": info["plural"],
                "namespaced": info["namespaced"],
                "note": info["note"],
                "authorable": info["authorable"],
                "category": info["category"],
            },
            "app_version": __version__,
        },
    )


@app.get("/api/kinds")
def api_kinds(version: str | None = None) -> Any:
    version = version or default_version()
    return {"version": version, "kinds": _kinds(version)}


@app.get("/api/presets")
def api_presets() -> Any:
    """The kinds that have a hand-written starting-point manifest."""
    return {"kinds": list(curated_kinds())}


@app.get("/api/tree")
def api_tree(apiVersion: str, kind: str, version: str | None = None) -> Any:
    version = version or default_version()
    return {
        "tree": _client_tree(_widget_tree(version, kind, apiVersion)),
        "preset": preset_for(kind),
    }


@app.post("/api/render")
def api_render(request: RenderRequest) -> Any:
    version = request.version or default_version()
    validator = _validator(version)
    issues: list[Issue] = []
    bundle: list[dict[str, Any]] = []

    for index, entry in enumerate(request.objects):
        manifest = dict(entry.manifest)
        manifest.setdefault("apiVersion", entry.apiVersion)
        manifest.setdefault("kind", entry.kind)
        try:
            tree = _widget_tree(version, entry.kind, entry.apiVersion)
        except SchemaError as exc:
            issues.append(Issue("error", "unknown-kind", str(exc), object_index=index))
            bundle.append(manifest)
            continue
        for issue in check_form(tree, manifest):
            issue.object_index = index
            issues.append(issue)
        for issue in validator.check(manifest):
            issue.object_index = index
            issues.append(issue)
        bundle.append(manifest)

    issues.extend(analyse(bundle))
    yaml_text = to_bundle_yaml(bundle)
    return {
        "ok": not any(issue.level == "error" for issue in issues),
        "yaml": yaml_text,
        "issues": [issue.to_dict() for issue in issues],
        "objects": bundle,
    }


@app.post("/api/validate")
def api_validate(request: ValidateRequest) -> Any:
    """Validate a pasted YAML file and re-render it in canonical form."""
    version = request.version or default_version()
    try:
        documents = parse_yaml(request.yaml)
    except yaml.YAMLError as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": f"Could not parse YAML: {exc}",
                "issues": [],
                "yaml": "",
            },
            status_code=400,
        )
    validator = _validator(version)
    issues: list[Issue] = []
    for index, document in enumerate(documents):
        kind = document.get("kind", "")
        api_version = document.get("apiVersion", "")
        try:
            tree = _widget_tree(version, kind, api_version)
        except SchemaError:
            tree = None
        if tree is not None:
            for issue in check_form(tree, document):
                issue.object_index = index
                issues.append(issue)
        for issue in validator.check(document):
            issue.object_index = index
            issues.append(issue)
    issues.extend(analyse(documents))
    return {
        "ok": not any(issue.level == "error" for issue in issues),
        "yaml": to_bundle_yaml(documents),
        "issues": [issue.to_dict() for issue in issues],
        "objects": documents,
    }


@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    return "ok"
