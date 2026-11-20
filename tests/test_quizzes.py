from __future__ import annotations

import re

import pytest

from kyamlgen.quizzes import (
    Question,
    _curated,
    curated_for,
    curated_kinds,
    derived_for,
    quiz_for,
    render_questions,
    shuffled,
)
from kyamlgen.schemas import kind_index, load_bundle
from kyamlgen.widgets import WidgetBuilder

VERSION = "1.31.0"

#: A link to another kind's form inside an explanation.
KIND_LINK_RE = re.compile(r"/form\?apiVersion=([^&\"]+)&amp;kind=([A-Za-z0-9]+)")
#: A link to a field in the form inside an explanation.
FIELD_LINK_RE = re.compile(r"field:([A-Za-z0-9_.\[\]]+)")

BUNDLE = load_bundle(VERSION)
BUNDLE_KINDS = {ref.kind for ref in kind_index(VERSION).values()}


def prose_path(path: list[str]) -> str:
    """Turn a widget tree path into the prose form a question would use."""
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


def test_there_are_twenty_nine_curated_quizzes() -> None:
    assert len(curated_kinds()) == 29


def test_there_are_about_two_hundred_questions() -> None:
    total = sum(len(questions) for questions in _curated().values())
    assert total >= 190, f"only {total} curated questions"


@pytest.mark.parametrize("kind", curated_kinds())
def test_curated_quiz_is_well_formed(kind: str) -> None:
    questions = curated_for(kind)
    assert questions, f"{kind} has no quiz"
    assert len(questions) >= 6, f"{kind} has only {len(questions)} questions"
    for question in questions:
        question.validate(kind)


@pytest.mark.parametrize("kind", curated_kinds())
def test_no_two_questions_in_a_quiz_are_the_same(kind: str) -> None:
    questions = curated_for(kind)
    assert questions
    prompts = [question.prompt for question in questions]
    assert len(prompts) == len(set(prompts)), f"{kind} has a repeated question"


@pytest.mark.parametrize("kind", curated_kinds())
def test_explanations_reference_real_fields_and_kinds(kind: str) -> None:
    """A link to a field that does not exist is a dead link."""
    questions = curated_for(kind)
    assert questions
    tree = WidgetBuilder(BUNDLE).build(kind, _api_version(kind))
    known = tree_paths(tree)

    for question in questions:
        for path in set(FIELD_LINK_RE.findall(question.why)):
            assert path in known, f"{kind}: explanation links to unknown field '{path}'"
        for _, linked in KIND_LINK_RE.findall(question.why):
            assert linked in BUNDLE_KINDS, f"{kind}: explanation links to unknown {linked}"


@pytest.mark.parametrize("kind", curated_kinds())
def test_options_are_not_trivially_guessable(kind: str) -> None:
    """The right answer must not always be in the same place."""
    questions = curated_for(kind)
    assert questions
    positions = {question.answer for question in questions}
    assert len(positions) > 1, f"{kind}: every answer is in the same position"


def test_every_kind_in_the_bundle_has_a_quiz() -> None:
    missing = []
    for ref in kind_index(VERSION).values():
        if not quiz_for(ref.kind, ref.api_version, VERSION):
            missing.append(f"{ref.api_version}/{ref.kind}")
    assert not missing, f"kinds with no quiz: {missing[:10]}"


def test_derived_quiz_works_for_a_kind_with_no_curated_one() -> None:
    questions = derived_for("ComponentStatus", "v1", VERSION)
    assert questions
    for question in questions:
        question.validate("ComponentStatus")


def test_derived_quiz_covers_every_kind_in_the_bundle() -> None:
    """The derived tier must not fall over on any kind."""
    failures = []
    for ref in kind_index(VERSION).values():
        if ref.kind in curated_kinds():
            continue
        try:
            questions = derived_for(ref.kind, ref.api_version, VERSION)
        except Exception as exc:  # pragma: no cover - diagnostic
            failures.append(f"{ref.api_version}/{ref.kind}: {exc}")
            continue
        if not questions:
            failures.append(f"{ref.api_version}/{ref.kind}: no questions")
            continue
        for question in questions:
            try:
                question.validate(ref.kind)
            except ValueError as exc:
                failures.append(f"{ref.api_version}/{ref.kind}: {exc}")
    assert not failures, "\n".join(failures[:10])


def test_shuffling_moves_the_answer_but_keeps_it() -> None:
    question = Question(
        prompt="Which one?",
        options=("a", "b", "c", "d"),
        answer=0,
        why="Because.",
    )
    for _ in range(20):
        result = shuffled([question])[0]
        assert set(result.options) == {"a", "b", "c", "d"}
        assert result.options[result.answer] == "a"


def test_rendered_html_hides_the_answer_until_the_learner_answers() -> None:
    questions = [
        Question(
            prompt="Which one?",
            options=("right", "wrong one", "wrong two", "wrong three"),
            answer=0,
            why="Because.",
        )
    ]
    html = render_questions(questions)
    assert 'class="question"' in html
    assert "checked" not in html, "the answer must not be pre-selected"
    assert 'class="answer" hidden' in html


def test_rendered_html_points_at_the_right_option() -> None:
    """After a shuffle, data-answer must still index the correct option."""
    question = Question(
        prompt="Which one?",
        options=("right", "wrong one", "wrong two", "wrong three"),
        answer=0,
        why="Because.",
    )
    for _ in range(20):
        html = render_questions([question])
        answer = int(re.search(r'data-answer="(\d+)"', html).group(1))
        options = re.findall(r"<span>([^<]*)</span>", html)
        assert options[answer] == "right"


def test_rendered_html_marks_the_right_option_after_a_shuffle() -> None:
    question = Question(
        prompt="Which one?",
        options=("right", "wrong one", "wrong two", "wrong three"),
        answer=0,
        why="Because.",
    )
    html = render_questions([question])
    # The correct option is wherever the shuffle put it.
    assert html.count(">right<") == 1
    assert "data-answer=" in html


def _api_version(kind: str) -> str:
    for ref in kind_index(VERSION).values():
        if ref.kind == kind:
            return ref.api_version
    raise AssertionError(f"unknown kind {kind}")
