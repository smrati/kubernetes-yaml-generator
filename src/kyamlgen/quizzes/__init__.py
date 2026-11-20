"""Multiple-choice questions for each kind.

A question is structured data rather than prose, because a quiz has to be scored:

    kind: Deployment
    questions:
      - prompt: >-
          A Deployment's selector does not match the labels on its own pod
          template. What happens?
        options:
          - The API server rejects the Deployment
          - The Deployment is accepted and manages no pods at all
          - The Deployment's existing pods are deleted
          - The Deployment falls back to selecting pods by name
        answer: 1
        why: >-
          The selector is how the Deployment says which Pods are its own.

Two tiers, as with the templates and the tutorials:

* **Curated** — hand-written questions for the kinds a course walks. These are the
  ones worth having: they target a misconception or a silent failure, not a field
  name.
* **Derived** — generated from what the tool already knows, for every other kind.
  Scope, required fields, permitted values. Recall rather than understanding, but it
  means no kind opens with nothing.

Options are shuffled before they are rendered. A quiz whose answer is always in the
same place teaches the position, not the material.
"""

from __future__ import annotations

import functools
import html
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..registry import CLUSTER_SCOPED, describe
from ..schemas import kind_index, load_bundle
from ..widgets import WidgetBuilder

#: Directory holding the hand-written quizzes, one YAML file per kind.
CURATED_DIR = Path(__file__).parent / "curated"

#: Questions are rendered as four options where possible.
OPTION_COUNT = 4

#: A question needs at least this many options to be worth asking.
MIN_OPTIONS = 2

#: How deep a field path may be and still be used as an option in a question.
MAX_PATH_DEPTH = 2


@dataclass(frozen=True)
class Question:
    """One multiple-choice question."""

    prompt: str
    options: tuple[str, ...]
    answer: int
    why: str

    def validate(self, kind: str) -> None:
        """Raise if the question is malformed."""
        if not self.prompt.strip():
            raise ValueError(f"{kind}: a question has no prompt")
        if len(self.options) < MIN_OPTIONS:
            raise ValueError(f"{kind}: a question needs at least two options")
        if len(set(self.options)) != len(self.options):
            raise ValueError(f"{kind}: a question has duplicate options")
        if any(not option.strip() for option in self.options):
            raise ValueError(f"{kind}: a question has an empty option")
        if not 0 <= self.answer < len(self.options):
            raise ValueError(f"{kind}: the answer index is out of range")
        if not self.why.strip():
            raise ValueError(f"{kind}: a question has no explanation")


# -- curated content --------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _curated() -> dict[str, tuple[Question, ...]]:
    """Every curated quiz, keyed by kind."""
    out: dict[str, tuple[Question, ...]] = {}
    for path in sorted(CURATED_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text()) or {}
        kind = document.get("kind") or path.stem
        questions = []
        for entry in document.get("questions") or []:
            question = Question(
                prompt=str(entry.get("prompt", "")).strip(),
                options=tuple(str(option).strip() for option in entry.get("options") or []),
                answer=int(entry.get("answer", -1)),
                why=str(entry.get("why", "")).strip(),
            )
            question.validate(kind)
            questions.append(question)
        out[kind] = tuple(questions)
    return out


@functools.lru_cache(maxsize=1)
def curated_kinds() -> tuple[str, ...]:
    """The kinds that have a hand-written quiz, sorted."""
    return tuple(sorted(_curated()))


def curated_for(kind: str) -> tuple[Question, ...] | None:
    """The hand-written quiz for a kind, if there is one."""
    return _curated().get(kind)


# -- derived quizzes --------------------------------------------------------


def prose_path(path: list[str]) -> str:
    """Turn a widget tree path into the prose form a question would use.

    ``["spec", "ports", "*", "port"]`` becomes ``spec.ports[].port``.
    """
    out: list[str] = []
    for segment in path:
        if segment == "*":
            out[-1] = out[-1] + "[]"
        else:
            out.append(segment)
    return ".".join(out)


def _top_level_paths(tree: dict[str, Any]) -> tuple[set[str], set[str]]:
    """The required and optional field paths of a kind, one level deep."""
    required: set[str] = set()
    optional: set[str] = set()

    def walk(node: dict[str, Any], depth: int) -> None:
        for child in node.get("children") or []:
            path = child.get("path") or []
            if len(path) <= MAX_PATH_DEPTH:
                if child.get("required"):
                    required.add(prose_path(path))
                else:
                    optional.add(prose_path(path))
            if len(path) < MAX_PATH_DEPTH:
                walk(child, depth + 1)

    walk(tree, 0)
    return required, optional


def _enum_fields(tree: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """Every field in a kind that has a curated list of permitted values."""
    found: list[tuple[str, list[str]]] = []

    def walk(node: dict[str, Any], path: list[str]) -> None:
        for child in node.get("children") or []:
            child_path = path + [child["name"]]
            if child.get("kind") == "select" and child.get("enum"):
                found.append((prose_path(child_path), list(child["enum"])))
            walk(child, child_path)
        item = node.get("item")
        if item:
            walk(item, path + ["*"])

    walk(tree, [])
    return found


def _cluster_scoped_kinds() -> list[str]:
    return sorted(CLUSTER_SCOPED)


def derived_for(kind: str, api_version: str, version: str) -> list[Question]:
    """Questions generated from what the tool knows about a kind."""
    bundle = load_bundle(version, strict=True)
    tree = WidgetBuilder(bundle).build(kind, api_version)
    info = describe(
        next(
            ref
            for ref in kind_index(version).values()
            if ref.kind == kind and ref.api_version == api_version
        )
    )
    questions: list[Question] = []

    # 1. Scope.  Always available.
    if info.namespaced:
        others = [name for name in _cluster_scoped_kinds() if name != kind][:3]
        options = [kind, *others]
        questions.append(
            Question(
                prompt="Which of these kinds is namespaced?",
                options=tuple(options),
                answer=0,
                why=(
                    f"{kind} is namespaced, so every {kind} lives inside a namespace and "
                    f"is addressed as <name>.<namespace>. The others are cluster-scoped: "
                    f"one per cluster, not per namespace."
                ),
            )
        )
    else:
        others = [name for name in ("ConfigMap", "Role", "Pod", "Deployment") if name != kind][:3]
        options = [kind, *others]
        questions.append(
            Question(
                prompt="Which of these kinds is cluster-scoped?",
                options=tuple(options),
                answer=0,
                why=(
                    f"{kind} is cluster-scoped: there is one per cluster, and it lives "
                    f"outside any namespace. The others are namespaced."
                ),
            )
        )

    # 2. A required field.
    required, optional = _top_level_paths(tree)
    if required:
        answer = sorted(required)[0]
        # A distractor that is a prefix of the answer -- or that the answer is a
        # prefix of -- would be defensible, and a question with two defensible
        # answers is not a question.  "metadata" must not be offered against
        # "metadata.name".
        distractors = [
            path
            for path in sorted(optional - required)
            if not path.startswith(answer + ".") and not answer.startswith(path + ".")
        ][:3]
        if len(distractors) >= MIN_OPTIONS:
            questions.append(
                Question(
                    prompt=f"Which of these fields is required when you create a {kind}?",
                    options=(answer, *distractors),
                    answer=0,
                    why=(
                        f"`{answer}` is required. The API server rejects a {kind} "
                        f"without it — which is why the form marks it."
                    ),
                )
            )

    # 3. A permitted value.
    enums = [
        (path, values)
        for path, values in _enum_fields(tree)
        if "*" not in path and path.split(".")[-1] not in ("apiVersion", "kind")
    ]
    if enums:
        path, values = enums[0]
        correct = values[0]
        pool = [
            value for _name, other in _enum_fields(tree) for value in other if value not in values
        ]
        distractors = list(dict.fromkeys(pool))[:3]
        if len(distractors) >= MIN_OPTIONS:
            questions.append(
                Question(
                    prompt=f"Which of these is a valid value for `{path}`?",
                    options=(correct, *distractors),
                    answer=0,
                    why=(
                        f"`{path}` accepts: {', '.join(values)}. The other values "
                        f"belong to different fields."
                    ),
                )
            )

    return questions


# -- assembly ---------------------------------------------------------------


def quiz_for(kind: str, api_version: str, version: str) -> list[Question]:
    """The quiz for a kind — curated, or derived when there is no curated one."""
    curated = curated_for(kind)
    if curated:
        return list(curated)
    return derived_for(kind, api_version, version)


def shuffled(questions: list[Question]) -> list[Question]:
    """Reorder each question's options so the answer is not always in one place."""
    out: list[Question] = []
    for question in questions:
        options = list(question.options)
        correct = options[question.answer]
        random.shuffle(options)
        out.append(
            Question(
                prompt=question.prompt,
                options=tuple(options),
                answer=options.index(correct),
                why=question.why,
            )
        )
    return out


def render_questions(questions: list[Question]) -> str:
    """Render a quiz as HTML.

    The answer index is in a data attribute, and the explanation is hidden until the
    learner has chosen.  The JavaScript that reveals it lives in ``static/quiz.js``.
    """
    blocks = []
    for index, question in enumerate(shuffled(questions)):
        options = []
        for option_index, option in enumerate(question.options):
            options.append(
                f'<label class="option">'
                f'<input type="radio" name="q{index}" value="{option_index}" />'
                f"<span>{html.escape(option)}</span>"
                f"</label>"
            )
        blocks.append(
            f'<div class="question" data-answer="{question.answer}">'
            f'<p class="question-prompt">{html.escape(question.prompt)}</p>'
            f'<div class="options">{"".join(options)}</div>'
            f'<div class="answer" hidden>'
            f'<span class="verdict"></span>'
            f'<p class="explanation">{html.escape(question.why)}</p>'
            f"</div>"
            f"</div>"
        )
    return "".join(blocks)
