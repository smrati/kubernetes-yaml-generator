from __future__ import annotations

import inspect
import re

import pytest

from kyamlgen import semantics
from kyamlgen.schemas import kind_index, load_bundle
from kyamlgen.semantics import RELATIONSHIPS, RULE_BY_CODE, RULES
from kyamlgen.tutorials import curated_for, curated_kinds, tutorial_for
from kyamlgen.widgets import WidgetBuilder

VERSION = "1.31.0"

#: A link to another kind's form inside a tutorial.
KIND_LINK_RE = re.compile(r"/form\?apiVersion=([^&\"]+)&amp;kind=([A-Za-z0-9]+)")
#: A link to a field in the form inside a tutorial.
FIELD_LINK_RE = re.compile(r"field:([A-Za-z0-9_.\[\]]+)")

#: Every kind link the tutorials use must point at a kind that exists.
BUNDLE = load_bundle(VERSION)
BUNDLE_KINDS = {ref.kind for ref in kind_index(VERSION).values()}


def prose_path(path: list[str]) -> str:
    """Turn a widget tree path into the prose form a tutorial would write.

    ``["spec", "ports", "*", "port"]`` becomes ``spec.ports[].port``.
    """
    out: list[str] = []
    for segment in path:
        if segment == "*":
            out[-1] = out[-1] + "[]"
        else:
            out.append(segment)
    return ".".join(out)


def tree_paths(tree: dict) -> set[str]:
    """Every path in a widget tree, in prose form."""

    def walk(node: dict) -> None:
        path = node.get("path") or []
        if path:
            paths.add(prose_path(path))
        for child in node.get("children", []):
            walk(child)
        item = node.get("item")
        if item:
            walk(item)

    paths: set[str] = set()
    walk(tree)
    return paths


def api_version_for(kind: str) -> str:
    """The API version the bundle uses for a kind."""
    for ref in kind_index(VERSION).values():
        if ref.kind == kind:
            return ref.api_version
    raise AssertionError(f"unknown kind {kind}")


def test_there_are_twenty_nine_curated_tutorials() -> None:
    assert len(curated_kinds()) == 29


@pytest.mark.parametrize("kind", curated_kinds())
def test_curated_tutorial_is_well_formed(kind: str) -> None:
    curated = curated_for(kind)
    assert curated is not None
    assert curated.kind == kind
    assert curated.summary.strip(), "a tutorial needs a summary"
    assert curated.body.strip(), "a tutorial needs a body"
    assert "## Use it for" in curated.body, "a tutorial should say when to use it"


@pytest.mark.parametrize("kind", curated_kinds())
def test_field_paths_in_a_tutorial_exist_in_the_form(kind: str) -> None:
    """A typo in a field path is a dead link, so it fails the build instead."""
    curated = curated_for(kind)
    assert curated is not None
    tree = WidgetBuilder(BUNDLE).build(kind, api_version_for(kind))
    known = tree_paths(tree)

    for path in set(FIELD_LINK_RE.findall(curated.body)):
        assert path in known, (
            f"{kind}: tutorial links to field '{path}', which is not in the form. "
            f"Known paths include: {sorted(known)[:10]}"
        )


@pytest.mark.parametrize("kind", curated_kinds())
def test_kind_links_point_at_kinds_that_exist(kind: str) -> None:
    curated = curated_for(kind)
    assert curated is not None
    for _, linked in KIND_LINK_RE.findall(curated.body):
        assert linked in BUNDLE_KINDS, f"{kind}: tutorial links to unknown kind {linked}"


def test_every_kind_in_the_bundle_has_a_tutorial() -> None:
    """No kind should open with nothing at all."""
    missing = []
    for ref in kind_index(VERSION).values():
        if tutorial_for(ref.kind, ref.api_version, VERSION) is None:
            missing.append(f"{ref.api_version}/{ref.kind}")
    assert not missing, f"kinds with no tutorial: {missing[:10]}"


def test_a_curated_tutorial_is_used_when_one_exists() -> None:
    tutorial = tutorial_for("Deployment", "apps/v1", VERSION)
    assert tutorial is not None
    assert tutorial.curated is True
    assert "Deployment" in tutorial.lead_html


def test_a_derived_tutorial_falls_back_to_the_schema_description() -> None:
    tutorial = tutorial_for("ComponentStatus", "v1", VERSION)
    assert tutorial is not None
    assert tutorial.curated is False
    assert tutorial.summary
    assert tutorial.scope


def test_tutorial_connections_name_the_other_side() -> None:
    """The counterpart set depends on which side you are reading from."""
    deployment = tutorial_for("Deployment", "apps/v1", VERSION)
    assert deployment is not None
    counterparts = {kind for c in deployment.connections for kind in c["kinds"]}
    assert "Service" in counterparts
    assert "ConfigMap" in counterparts
    # Peers are not counterparts: a Deployment does not connect to a StatefulSet.
    assert "StatefulSet" not in counterparts

    service = tutorial_for("Service", "v1", VERSION)
    assert service is not None
    service_counterparts = {kind for c in service.connections for kind in c["kinds"]}
    assert "Ingress" in service_counterparts
    assert "Deployment" in service_counterparts


def test_every_relationship_names_a_real_rule() -> None:
    for relationship in RELATIONSHIPS:
        if relationship.rule is None:
            continue
        assert relationship.rule in RULE_BY_CODE, relationship.rule
        rule = RULE_BY_CODE[relationship.rule]
        for kind in (*relationship.initiator, *relationship.target):
            assert rule.involves(kind), f"{relationship.rule} does not cover {kind}"


def test_tutorial_checks_come_from_the_rule_table() -> None:
    tutorial = tutorial_for("Deployment", "apps/v1", VERSION)
    assert tutorial is not None
    rules = {check["rule"] for check in tutorial.checks}
    assert "selector-template-mismatch" in rules
    assert "image-no-tag" in rules


def test_every_rule_code_is_documented() -> None:
    """The tutorial describes the checks; a check with no description is a gap."""
    documented = {rule.code for rule in RULES}
    assert len(documented) == len(RULES), "duplicate rule codes"

    source = inspect.getsource(semantics)
    emitted = set(re.findall(r'code="([a-z0-9-]+)"', source))
    emitted |= set(re.findall(r'"([a-z-]+-ref-missing)"', source))
    assert emitted <= documented, f"undocumented rule codes: {emitted - documented}"
    assert documented <= emitted | {"namespace-mismatch"}, (
        f"documented but never emitted: {documented - emitted}"
    )


def test_tutorial_text_rendering_has_content() -> None:
    tutorial = tutorial_for("Service", "v1", VERSION)
    assert tutorial is not None
    text = tutorial.to_text()
    assert "Service" in text
    assert "<" not in text, "the text rendering should have no HTML in it"
