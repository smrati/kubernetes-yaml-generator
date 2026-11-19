"""Curated tutorials and the machinery that assembles them.

A tutorial has two halves, and the split matters:

* The **curated** half is the judgement — what the kind is for, when to reach for
  something else instead, and the guidance that only a person can write.  It lives
  in ``curated/<kind>.md`` as Markdown.
* The **derived** half is everything the tool already knows — how the kind connects
  to other kinds, which checks apply to it, whether it is namespaced, and who
  normally creates it.  It is generated from the schema, the rule table and the
  kind registry, so it cannot go stale.

The derived half is what makes the tool a teacher rather than a form: the
connections come from the same table the checker uses, so the tutorial and the
checker can never disagree about what is connected to what.
"""

from __future__ import annotations

import functools
import html
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import markdown
import yaml

from ..presets import preset_for
from ..registry import OWNED_BY_KIND, describe
from ..render import to_yaml
from ..schemas import KindRef, default_version, kind_index, load_bundle
from ..semantics import relationships_for, rules_for
from ..widgets import WidgetBuilder

#: Directory holding the hand-written tutorials, one Markdown file per kind.
CURATED_DIR = Path(__file__).parent / "curated"

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)


@dataclass(frozen=True)
class Tutorial:
    """A rendered tutorial for one kind."""

    kind: str
    api_version: str
    summary: str
    lead_html: str
    curated: bool
    connections: list[dict[str, Any]] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    example_yaml: str | None = None
    scope: dict[str, Any] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)

    @property
    def sections(self) -> list[tuple[str, str]]:
        """The collapsible sections below the lead, as (heading, html)."""
        out: list[tuple[str, str]] = []
        if self.connections:
            out.append(("How it connects", _connections_html(self.connections)))
        if self.checks:
            out.append(("What the tool checks for you", _checks_html(self.checks)))
        if self.example_yaml:
            out.append(("Worked example", _example_html(self.example_yaml)))
        if self.scope:
            out.append(("Scope and ownership", _scope_html(self.scope)))
        return out

    def to_text(self) -> str:
        """A plain-text rendering, for the terminal."""
        parts = [self.summary, "", _strip_tags(self.lead_html)]
        for heading, body in self.sections:
            parts.append("")
            parts.append(heading)
            parts.append("-" * len(heading))
            parts.append(_strip_tags(body))
        return "\n".join(parts).strip() + "\n"


# -- curated content --------------------------------------------------------


@dataclass(frozen=True)
class Curated:
    """A hand-written tutorial: front matter plus a Markdown body."""

    kind: str
    summary: str
    body: str


@functools.lru_cache(maxsize=1)
def _curated() -> dict[str, Curated]:
    """Every curated tutorial, keyed by kind."""
    out: dict[str, Curated] = {}
    for path in sorted(CURATED_DIR.glob("*.md")):
        text = path.read_text()
        match = _FRONT_MATTER_RE.match(text)
        if not match:
            raise ValueError(f"{path.name} has no front matter")
        front = yaml.safe_load(match.group(1)) or {}
        kind = front.get("kind") or path.stem
        out[kind] = Curated(
            kind=kind,
            summary=front.get("summary", ""),
            body=match.group(2).strip(),
        )
    return out


@functools.lru_cache(maxsize=1)
def curated_kinds() -> tuple[str, ...]:
    """The kinds that have a hand-written tutorial, sorted."""
    return tuple(sorted(_curated()))


def curated_for(kind: str) -> Curated | None:
    """The hand-written tutorial for a kind, if there is one."""
    return _curated().get(kind)


# -- assembly ---------------------------------------------------------------


def tutorial_for(
    kind: str,
    api_version: str,
    version: str = "1.37.0",
) -> Tutorial | None:
    """Build the tutorial for a kind, curated or derived.

    Returns ``None`` only when the kind does not exist in the schema bundle.
    """
    ref = _find_ref(kind, api_version, version)
    if ref is None:
        return None

    curated = curated_for(kind)
    bundle = load_bundle(version, strict=True)
    schema = bundle.kind_schema(kind, api_version)

    if curated is not None:
        summary = curated.summary
        lead = _render_markdown(curated.body)
    else:
        summary = _first_sentence(schema.get("description", ""))
        lead = ""

    info = describe(ref)
    return Tutorial(
        kind=kind,
        api_version=api_version,
        summary=summary,
        lead_html=lead,
        curated=curated is not None,
        connections=_connections(kind),
        checks=[{"rule": rule.code, "summary": rule.summary} for rule in rules_for(kind)],
        example_yaml=_example_for(kind),
        scope={
            "namespaced": info.namespaced,
            "owner": info.owner,
            "note": info.note,
            "plural": info.plural,
        },
        required=_required_paths(bundle, kind, api_version),
    )


def _find_ref(kind: str, api_version: str, version: str) -> KindRef | None:
    for ref in kind_index(version).values():
        if ref.kind == kind and ref.api_version == api_version:
            return ref
    return None


def _first_sentence(text: str) -> str:
    """The first sentence of a description, for a one-line summary."""
    text = " ".join((text or "").split())
    if not text:
        return ""
    match = re.search(r"(?<=[.!?])\s", text)
    return text[: match.start() + 1] if match else text


def _render_markdown(body: str) -> str:
    """Render Markdown to HTML.

    The content is our own, shipped in the package, so raw HTML passing through is
    not a concern.  Links of the form ``field:spec.replicas`` are left alone; the
    browser turns them into a jump to that field in the form.
    """
    if not body:
        return ""
    return markdown.markdown(body, extensions=["extra", "sane_lists"])


def _example_for(kind: str) -> str | None:
    """The worked example for a kind — its template, if it has one."""
    manifest = preset_for(kind)
    return to_yaml(manifest) if manifest else None


def _connections(kind: str) -> list[dict[str, Any]]:
    """The kinds a kind connects to, and the check that catches a mismatch.

    The relationships are curated in :mod:`kyamlgen.semantics`, because "which kinds
    reference each other" is a different question from "which checks apply to this
    kind" and only the first is worth teaching.
    """
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for relationship in relationships_for(kind):
        key = tuple(relationship["kinds"])
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "rule": relationship["rule"],
                "kinds": list(relationship["kinds"]),
                "summary": relationship["sentence"],
            }
        )

    owners = OWNED_BY_KIND.get(kind)
    if owners:
        out.append(
            {
                "rule": None,
                "kinds": list(owners),
                "summary": (
                    f"A {kind} is normally created by {_join(owners)}, not by you. "
                    f"Authoring one means taking over that controller's job."
                ),
            }
        )
    return out


def _required_paths(bundle, kind: str, api_version: str) -> list[str]:
    """The field paths the API server requires."""
    tree = WidgetBuilder(bundle).build(kind, api_version)
    found: list[str] = []

    def walk(node: dict, path: list[str]) -> None:
        if node.get("required") and path:
            found.append(".".join(path))
        for child in node.get("children", []):
            walk(child, [*path, child["name"]])
        item = node.get("item")
        if item:
            walk(item, [*path, "*"])

    for child in tree.get("children", []):
        walk(child, [child["name"]])
    return found


# -- HTML fragments ---------------------------------------------------------


def _kind_link(kind: str) -> str:
    """A link to another kind's form, if that kind is in the bundle."""
    for ref in kind_index(default_version()).values():
        if ref.kind == kind:
            return (
                f'<a href="/form?apiVersion={html.escape(ref.api_version)}'
                f'&amp;kind={html.escape(kind)}">{html.escape(kind)}</a>'
            )
    return html.escape(kind)


def _join(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _connections_html(connections: list[dict[str, Any]]) -> str:
    rows = []
    for connection in connections:
        links = ", ".join(_kind_link(kind) for kind in connection["kinds"])
        rule = connection.get("rule")
        check = (
            f'<span class="tutorial-rule">checked by <code>{html.escape(rule)}</code></span>'
            if rule
            else ""
        )
        rows.append(
            f'<li><span class="tutorial-kinds">{links}</span> — '
            f"{html.escape(connection['summary'])} {check}</li>"
        )
    return f'<ul class="tutorial-list">{"".join(rows)}</ul>'


def _checks_html(checks: list[dict[str, Any]]) -> str:
    rows = [
        f"<li><code>{html.escape(check['rule'])}</code> — {html.escape(check['summary'])}</li>"
        for check in checks
    ]
    return f'<ul class="tutorial-list">{"".join(rows)}</ul>'


def _example_html(example: str) -> str:
    return f'<pre class="tutorial-example">{html.escape(example)}</pre>'


def _scope_html(scope: dict[str, Any]) -> str:
    rows = []
    rows.append(
        "<li><strong>Scope:</strong> "
        + (
            "namespaced — every object of this kind lives inside a namespace."
            if scope.get("namespaced")
            else "cluster-scoped — one object per cluster, not per namespace."
        )
        + "</li>"
    )
    rows.append(
        f"<li><strong>Plural:</strong> <code>{html.escape(scope.get('plural', ''))}</code></li>"
    )
    owner = scope.get("owner")
    if owner:
        rows.append(f"<li><strong>Normally created by:</strong> {html.escape(owner)}.</li>")
    note = scope.get("note")
    if note:
        rows.append(f'<li class="tutorial-note">{html.escape(note)}</li>')
    return f'<ul class="tutorial-list">{"".join(rows)}</ul>'


def _strip_tags(text: str) -> str:
    """A plain-text rendering of an HTML fragment."""
    text = re.sub(r"<li>", "\n- ", text)
    text = re.sub(r"</?(ul|ol|p|h[1-6]|pre|div)[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
