# kyamlgen

Form-driven Kubernetes YAML generator. Fill in a form, get correct YAML you can
`kubectl apply`.

## What this repo is

The **source workspace** for the tool. It is a local FastAPI application that
generates Kubernetes manifests from a schema-driven form and validates them — both
individually and as a bundle, across objects.

## Read these first

| File | Role |
|---|---|
| `architecture.md` | **Design of record** — what the system is and how it works. Decision index D1–D11. |
| `INTENT.md` | **Append-only decision log** — why each decision was made. Newest entry at the bottom. |

Read `architecture.md` before making any structural change. Do not duplicate its
content here.

### The two-document convention (don't break this)

- `architecture.md` = *what*. Never edit it silently.
- `INTENT.md` = *why*. Append-only, newest entry at the bottom.
- Every meaningful architecture change requires all three:
  1. a new dated entry in `INTENT.md` with **Asked / Decided / Why / Affects**,
     separated by `---`;
  2. the corresponding section of `architecture.md` updated;
  3. a new `D#` anchor in the §3 decision index if it introduces a new decision.
- The user has asked to be consulted when a decision needs their input — ask, don't
  guess.

## Current state

M1 complete; M2 and M3 substantially done. `architecture.md` §13 has the honest
status table. M4 (server dry-run against a real cluster) is the only milestone
blocked on infrastructure.

## Stack and commands

- Python 3.13 (`.python-version`), managed with **uv**. Never invoke `pip`
  directly.
- `uv sync` to install, `uv add <pkg>` to add a dependency, `uv run <cmd>` to run.
- `uv run kyamlgen serve` — the web app on <http://127.0.0.1:8000>.
- `uv run kyamlgen kinds` — every kind in the schema bundle.
- `uv run kyamlgen tree <Kind> --api-version <group/version>` — the widget tree as
  JSON.
- `uv run kyamlgen generate <Kind> --api-version <group/version> --values file.json`
  — a manifest from JSON values, without a browser.
- `uv run kyamlgen validate manifest.yaml` — validate a file.
- `uv run pytest` — the test suite.
- `uv run ruff check src tests` — lint. `uv run ruff format src tests` to format.
  Both are configured in `pyproject.toml`; keep them passing.

## Module map

| Module | Responsibility |
|---|---|
| `schemas.py` | Locate the bundled Kubernetes schemas, index the kinds, resolve `$ref` |
| `widgets.py` | Schema → widget tree; curated enums, bounds, required fields, visibility |
| `registry.py` | What the schema cannot say: scope, plural, ownership, categories |
| `validate.py` | Form-time checks and JSON Schema validation |
| `semantics.py` | Cross-object rules over a bundle |
| `render.py` | Pruning, key ordering, YAML output |
| `app.py` | FastAPI routes |
| `cli.py` | `serve` / `kinds` / `tree` / `generate` / `validate` |
| `static/formstate.js` | The form's data-path logic — shared by the browser and the Node tests |

## Ground rules — do not relax these

1. **The schema is the source of truth.** Field names, types and required fields
   come from the bundled Kubernetes schema, never from hand-written lists. If a
   field is missing, the schema is wrong, not the form.
2. **Never invent a field name.** A field the schema does not have does not exist.
   The curated tables in `widgets.py` (`FIELD_ENUMS`, `ITEM_ENUMS`, `FIELD_RANGES`,
   `EXTRA_REQUIRED`, `COMMON_PROPERTIES`) are *additions* to the schema, never
   replacements for it, and each one carries a comment saying why.
3. **Never offer a server-owned field.** `status` and the API-server-owned
   `ObjectMeta` fields are excluded at build time, not hidden in the UI.
4. **Keep the four validation layers separate.** Form-time, JSON Schema, semantic,
   server dry-run. Each catches a class the others cannot; merging them destroys
   the value of each.
5. **Semantic errors are for things that are actually broken.** A reference to a
   ConfigMap that is not in the bundle is a *warning*, because the object may exist
   in the cluster. Reserve errors for agreements that would silently break traffic.
6. **YAML output is read by people.** Apply the key preference list, and keep
   user-keyed maps in the user's order. Do not switch to `ruamel.yaml` — see
   `INTENT.md`, 2026-11-19.
7. **No cluster, no network, no problem.** Everything except M4 works offline. Do
   not add a dependency on a reachable API server.
8. **Test the rules, not the implementation.** Every semantic rule and every
   curated table needs a test that fails when the rule is wrong.
9. **The renderer must not create data.** Reading a container in the browser may
   never create one — only typing into a field or pressing "Add" may. A renderer
   that fills in the structure it walks through turns every advanced field it
   displays into an empty object in the submission, and the server then reports
   their missing required children as real errors. `formstate.js` separates
   `readContainer` from `ensureContainer` for exactly this reason.

## Tests

`uv run pytest` runs everything: 64 Python tests, plus a wrapper that runs the 12
JavaScript tests under `node --test`. 65 checks in total, one command.

| File | Covers |
|---|---|
| `test_schemas.py` | Bundle layout, file naming, `$ref` resolution, kind index |
| `test_widgets.py` | Widget mapping, required fields, visibility, recursion guard, **every kind builds** |
| `test_validation.py` | Form-time checks, schema validation, every semantic rule |
| `test_render.py` | Key ordering, YAML 1.1 quoting, pruning, multi-document output |
| `test_api.py` | End-to-end HTTP behaviour |
| `test_javascript.py` | Runs `tests/js/formstate.test.js` under `node --test` |
| `js/formstate.test.js` | The form's path arithmetic: `getIn`, `setIn`, `readContainer`, `ensureContainer` |

Two of these matter more than the rest:

- `test_widgets.py::test_every_kind_in_the_bundle_builds_a_tree` walks every kind in
  the schema bundle and fails if any of them breaks the form engine.
- `js/formstate.test.js::reading a path never disturbs the data` pins the bug
  described in rule 9 above.
