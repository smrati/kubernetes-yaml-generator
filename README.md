# kyamlgen — Kubernetes YAML generator

Fill in a form, get correct YAML you can paste into a file and `kubectl apply`.

Most Kubernetes YAML is not hard because the fields are complicated — it is hard because
there are **two** problems, and only one of them is a knowledge problem:

1. **Knowledge** — which fields exist, what type they are, which are required, which
   `apiVersion` is current. The Kubernetes API schema already encodes all of this, so the
   form is generated from the schema rather than hand-written.
2. **Coupling** — the same value has to appear in several places, and the places drift
   silently. A Deployment with a typo in `spec.selector.matchLabels` deploys perfectly and
   then serves zero traffic, because the Service no longer matches its pods.

`kyamlgen` solves (1) with a schema-driven form engine and solves (2) with a semantic
engine that understands how Kubernetes objects reference each other.

## Quick start

```bash
uv sync
uv run kyamlgen serve          # http://127.0.0.1:8000
```

Then open <http://127.0.0.1:8000>, pick a resource kind, fill the form, and copy the YAML.

## How it works

```
Browser (vanilla JS, no build step)
   │  POST /api/render
FastAPI
 ├── schema service    bundled Kubernetes JSON schemas, $ref-resolved
 ├── kind registry     scope · plural · ownership · categories
 ├── form engine       schema -> widget tree
 ├── presets           hand-written starting-point manifests
 ├── tutorials         hand-written tutorials + the derived ones
 ├── semantic engine   coupling rules · reference checks · advisories
 ├── validator         form-time -> JSON Schema (strict) -> semantic
 ├── renderer          dict -> ordered YAML -> multi-document bundle
 └── CLI               serve · kinds · presets · preset · tutorial · tree · generate · validate
```

Validation runs in four layers, because each catches a different class of error:

| Layer | Catches |
|---|---|
| Form-time | out-of-range ports, malformed names, bad quantity syntax, invalid enum values |
| JSON Schema (strict) | unknown fields, wrong types, missing required fields |
| Semantic | selector/label mismatch, `targetPort` that matches no container port, dangling `ConfigMap` references |
| Server dry-run | admission control, defaulting, real API-server rejection — *planned, needs a cluster* |

## Tutorials

Every kind opens with a tutorial, in two tiers. **Twenty-nine kinds have a
hand-written one** — the workload, networking, configuration, storage, scaling and
access-control kinds a course actually walks. The rest get a derived one: the
schema's own description, the scope, who normally creates it, and how it connects
to other kinds.

The tutorial is not a page beside the form — it is wired into it:

- **Related kinds** are links to their own forms.
- **Field paths** in the prose are links that scroll the form to that field and
  flash it. `spec.selector.matchLabels` in the tutorial *is* that input.
- **How it connects** and **what the tool checks for you** are generated from the
  same tables the checker uses, so the tutorial cannot describe a check that does
  not exist.

```bash
uv run kyamlgen tutorial Deployment
```

## Templates

Seventeen common kinds open **pre-filled** with a hand-written template — a real,
working manifest, not a field-by-field walkthrough. Each one is filled only to the
level people actually use.

The Deployment and Service templates are designed to work together: same labels,
and the Service targets the *named* container port. Add both and the bundle
validates with zero findings.

Clearing is available at every granularity — a **×** on one field, **Clear** on a
whole section, **×** on a map row, **Remove** on an array item, plus **Clear
values** and **Reset to template** for the whole object. A **•** marks a field that
still holds the template's value.

```bash
uv run kyamlgen presets                        # kinds that have a template
uv run kyamlgen preset Deployment              # print one
uv run kyamlgen generate Deployment --api-version apps/v1 --preset
```

## From the command line

```bash
uv run kyamlgen kinds                        # every kind in the schema bundle
uv run kyamlgen tree Deployment --api-version apps/v1
uv run kyamlgen generate Deployment --api-version apps/v1 --values values.json
uv run kyamlgen validate manifest.yaml
```

## Tests

```bash
uv run pytest        # 211 Python tests, plus the 19 JavaScript tests they wrap
```

The suite covers the schema service, the widget engine (including a test that walks
*every* kind in the bundle), all four validation layers, the YAML renderer, every
template, every tutorial's links, and the HTTP API end to end.

## Status

See `architecture.md` §15 for the honest status table and §16 for the open
questions. `INTENT.md` is the append-only decision log explaining *why* each choice
was made.

## Licence

MIT
