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
 ├── semantic engine   coupling rules · reference checks · advisories
 ├── validator         form-time -> JSON Schema (strict) -> semantic
 ├── renderer          dict -> ordered YAML -> multi-document bundle
 └── CLI               serve · kinds · tree · generate · validate
```

Validation runs in four layers, because each catches a different class of error:

| Layer | Catches |
|---|---|
| Form-time | out-of-range ports, malformed names, bad quantity syntax, invalid enum values |
| JSON Schema (strict) | unknown fields, wrong types, missing required fields |
| Semantic | selector/label mismatch, `targetPort` that matches no container port, dangling `ConfigMap` references |
| Server dry-run | admission control, defaulting, real API-server rejection — *planned, needs a cluster* |

## From the command line

```bash
uv run kyamlgen kinds                        # every kind in the schema bundle
uv run kyamlgen tree Deployment --api-version apps/v1
uv run kyamlgen generate Deployment --api-version apps/v1 --values values.json
uv run kyamlgen validate manifest.yaml
```

## Tests

```bash
uv run pytest        # 64 Python tests, plus the 12 JavaScript tests they wrap
```

The suite covers the schema service, the widget engine (including a test that walks
*every* kind in the bundle), all four validation layers, the YAML renderer, and the
HTTP API end to end.

## Status

See `architecture.md` §13 for the honest status table and §14 for the open
questions. `INTENT.md` is the append-only decision log explaining *why* each choice
was made.

## Licence

MIT
