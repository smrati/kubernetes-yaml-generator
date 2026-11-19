"""Command line interface.

``kyamlgen serve`` is the main entry point; the rest exist so the tool can be used
from a terminal or a script as well as from a browser.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from . import __version__
from .registry import describe
from .render import parse_yaml, to_bundle_yaml
from .schemas import (
    SchemaError,
    default_version,
    kind_index,
    load_bundle,
)
from .semantics import analyse
from .validate import Issue, SchemaValidator, check_form
from .widgets import WidgetBuilder


def _kinds(version: str) -> list[Any]:
    seen = {}
    for ref in kind_index(version).values():
        seen.setdefault(ref.key, ref)
    return sorted(seen.values(), key=lambda ref: (ref.group, ref.kind))


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn  # noqa: PLC0415 - only the serve command needs the server stack

    uvicorn.run(
        "kyamlgen.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )
    return 0


def cmd_kinds(args: argparse.Namespace) -> int:
    version = args.version or default_version()
    for ref in _kinds(version):
        info = describe(ref)
        scope = "namespaced" if info.namespaced else "cluster"
        print(f"{info.api_version:40s} {info.kind:36s} {scope}")
    return 0


def cmd_tree(args: argparse.Namespace) -> int:
    version = args.version or default_version()
    bundle = load_bundle(version, strict=True)
    tree = WidgetBuilder(bundle).build(args.kind, args.api_version)
    json.dump(tree, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    """Build a manifest from a JSON file of field values."""
    version = args.version or default_version()
    bundle = load_bundle(version, strict=True)
    if args.values == "-":
        values = json.load(sys.stdin)
    else:
        values = json.loads(Path(args.values).read_text())

    manifest: dict[str, Any] = {
        "apiVersion": args.api_version,
        "kind": args.kind,
        "metadata": {},
    }
    manifest.update(values)
    manifest.setdefault("apiVersion", args.api_version)
    manifest.setdefault("kind", args.kind)

    tree = WidgetBuilder(bundle).build(args.kind, args.api_version)
    issues = check_form(tree, manifest)
    issues += SchemaValidator(bundle).check(manifest)
    issues += analyse([manifest])

    text = to_bundle_yaml([manifest])
    if args.out:
        Path(args.out).write_text(text)
    else:
        sys.stdout.write(text)

    for issue in issues:
        stream = sys.stderr if issue.level == "error" else sys.stdout
        print(f"{issue.level}: {issue.message}", file=stream)
    return 1 if any(issue.level == "error" for issue in issues) else 0


def cmd_validate(args: argparse.Namespace) -> int:
    version = args.version or default_version()
    bundle = load_bundle(version, strict=True)
    validator = SchemaValidator(bundle)

    text = sys.stdin.read() if args.path == "-" else Path(args.path).read_text()
    try:
        documents = parse_yaml(text)
    except yaml.YAMLError as exc:
        print(f"error: could not parse YAML: {exc}", file=sys.stderr)
        return 1

    issues: list[Issue] = []
    for index, document in enumerate(documents):
        kind = document.get("kind", "")
        api_version = document.get("apiVersion", "")
        try:
            tree = WidgetBuilder(bundle).build(kind, api_version)
        except SchemaError:
            tree = None
        if tree is not None:
            for issue in check_form(tree, document):
                issue.object_index = index
                issues.append(issue)
        for issue in validator.check(document):
            issue.object_index = index
            issues.append(issue)
    issues += analyse(documents)

    for issue in issues:
        stream = sys.stderr if issue.level == "error" else sys.stdout
        print(f"{issue.level}: {issue.message}", file=stream)
    if not issues:
        print("ok", file=sys.stdout)
    return 1 if any(issue.level == "error" for issue in issues) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kyamlgen", description="Form-driven Kubernetes YAML generator."
    )
    parser.add_argument("--version", action="version", version=f"kyamlgen {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the web application.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.add_argument("--log-level", default="info")
    serve.set_defaults(func=cmd_serve)

    kinds = sub.add_parser("kinds", help="List every kind in the schema bundle.")
    kinds.add_argument("--k8s-version", dest="version", default=None)
    kinds.set_defaults(func=cmd_kinds)

    tree = sub.add_parser("tree", help="Print the widget tree for a kind.")
    tree.add_argument("kind")
    tree.add_argument("--api-version", required=True)
    tree.add_argument("--k8s-version", dest="version", default=None)
    tree.set_defaults(func=cmd_tree)

    generate = sub.add_parser("generate", help="Build a manifest from JSON values.")
    generate.add_argument("kind")
    generate.add_argument("--api-version", required=True)
    generate.add_argument("--values", default="-", help="JSON file, or '-' for stdin.")
    generate.add_argument("--out", default=None, help="Write YAML here instead of stdout.")
    generate.add_argument("--k8s-version", dest="version", default=None)
    generate.set_defaults(func=cmd_generate)

    validate = sub.add_parser("validate", help="Validate a YAML manifest.")
    validate.add_argument("path", nargs="?", default="-")
    validate.add_argument("--k8s-version", dest="version", default=None)
    validate.set_defaults(func=cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except SchemaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
