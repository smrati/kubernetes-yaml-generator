# Architecture — kyamlgen

A form-driven Kubernetes YAML generator with cross-object semantic validation.

## How to read this document

- **§2** states what the tool must do, as testable requirements.
- **§3** is the decision index: every design decision (D1…Dn) maps to an entry in
  `INTENT.md` that records *why* it was taken.
- **§4** is the system architecture. The rest of the document walks each layer in
  the order data flows through it.
- **§12** is the quiz.
- **§13** is the renderer.
- **§14** is the web application.
- **§15** is the module layout.
- **§16** records what is built, what is not, and what comes next.
- **§17** lists the open questions.

`INTENT.md` is the append-only decision log. `architecture.md` is the design of record.
Neither duplicates the other: this document says *what*, `INTENT.md` says *why*.

Status: **M1 complete** — see §16.

---

## 1. Purpose and scope

Writing Kubernetes YAML by hand is hard for two different reasons, and only one of
them is a knowledge problem.

1. **Knowledge** — which fields exist, what type they are, which are required, which
   `apiVersion` is current, whether a field has been renamed. The Kubernetes API
   schema already encodes all of this, so the form should be generated from the
   schema rather than written by hand.
2. **Coupling** — the same value has to appear in several places, and the places drift
   silently. A Deployment whose `spec.selector.matchLabels` does not match its own
   `spec.template.metadata.labels` deploys perfectly and manages zero pods. A Service
   whose `targetPort` matches no container port serves 503s forever. No schema can
   catch either, because each object is individually valid.

`kyamlgen` solves (1) with a schema-driven form engine and solves (2) with a
semantic engine that understands how Kubernetes objects reference each other.

**In scope**

- All top-level kinds in the bundled Kubernetes schema — currently 193 distinct
  (group, kind) pairs across Kubernetes v1.25.0 – v1.37.0.
- Generating single objects and multi-document bundles.
- Validation in four layers, described in §8.
- A local web application and a CLI.

**Out of scope**

- Applying to a cluster (deferred to M4 — see §16).
- Custom Resource Definitions authored through the form (the schema for a CRD is
  self-referential; the engine falls back to raw JSON for the recursive part, §6.3).
- Hosting, accounts, persistence. The tool is local and stateless.

---

## 2. Requirements

| # | Requirement |
|---|---|
| R1 | The form for any kind must be derived from the Kubernetes schema, so field names, types and required fields are the API's and cannot drift. |
| R2 | Every kind in the schema bundle must be usable, including the ~130 kinds nobody hand-writes. |
| R3 | Field descriptions from the schema must be shown, so the form doubles as documentation. |
| R4 | The output must be valid YAML that `kubectl apply -f` accepts without hand-editing. |
| R5 | Unknown fields, wrong types and invalid enum values must be caught before the user leaves the page. |
| R6 | Cross-object agreements — selectors, ports, references, namespaces — must be checked across the whole bundle. |
| R7 | The tool must work offline, with no cluster and no network. |
| R8 | The tool must work with a browser but not require one; the CLI must expose the same capability. |
| R9 | Objects that a controller normally owns must be marked as such, because authoring them is a deliberate and usually wrong choice. |
| R10 | A field that the API server owns (`status`, `metadata.uid`, `resourceVersion`, …) must never be offered. |

---

## 3. Decision index

| # | Decision | Log entry |
|---|---|---|
| D1 | Forms are generated from the bundled Kubernetes schema, with curated overlays | 2026-11-19 |
| D2 | The tool is a local FastAPI application with a server-rendered shell and a JavaScript form renderer | 2026-11-19 |
| D3 | Scope is every kind in the bundle, including controller-owned kinds | 2026-11-19 |
| D4 | Schemas come from the `kubernetes-validate` bundle, offline | 2026-11-19 |
| D5 | Validation runs in four layers | 2026-11-19 |
| D6 | YAML is rendered with PyYAML, not ruamel.yaml | 2026-11-19 |
| D7 | Cross-object rules live in a semantic engine, not in string substitution | 2026-11-19 |
| D8 | The schema carries no enum data, so enums are curated by hand | 2026-11-19 |
| D9 | `status` and other server-owned fields are never offered | 2026-11-19 |
| D10 | The form is rendered by JavaScript from the widget tree; the server renders the page shell only | 2026-11-19 |
| D11 | The schema bundle's file naming is irregular, so the kind index is authoritative | 2026-11-19 |
| D12 | Presets are hand-written *manifests*, not form definitions; seventeen kinds have one | 2026-11-19 |
| D13 | A reference missing from the bundle is not a finding — the bundle is not the cluster | 2026-11-19 |
| D14 | Tutorials are hand-written Markdown for twenty-nine kinds, with a derived card for the rest | 2026-11-19 |
| D15 | The tutorial's connections and checks are derived from the checker's own tables | 2026-11-19 |
| D16 | Quizzes are structured data with a required explanation, and the options are shuffled | 2026-11-20 |

---

## 4. System architecture

```
Browser
  ├── index.html          kind picker, grouped by category, searchable
  ├── form.html           workbench: form on the left, YAML and issues on the right
  ├── app.js              renders the form from the widget tree
  └── picker.js           renders the kind catalogue
      │  POST /api/render  {version, objects: [{apiVersion, kind, manifest}]}
      ▼
FastAPI (kyamlgen/app.py)
  ├── schema service    (schemas.py)   locate the bundle, index kinds, resolve $ref
  ├── form engine       (widgets.py)   schema → widget tree
  ├── kind registry     (registry.py)  scope, plural, ownership, categories
  ├── validator         (validate.py)  form-time + JSON Schema
  ├── semantic engine   (semantics.py) cross-object rules
  └── renderer          (render.py)    dict → ordered YAML → multi-document bundle
```

The browser holds the form state and posts the resulting objects. The server never
reconstructs the form from posted markup; it re-derives the widget tree from the
schema, so the tree is always consistent with the schema bundle.

---

## 5. Schema service (`schemas.py`)

### 5.1 The bundle

`kubernetes-validate` ships the upstream Kubernetes OpenAPI schemas as an
installable package: v1.25.0 through v1.37.0, in two variants per version.

| Variant | Meaning |
|---|---|
| `v1.31.0-local` | Permissive. Unknown fields are accepted. |
| `v1.31.0-local-strict` | `additionalProperties: false` on 622 of the 635 definitions. Unknown fields are rejected. |

`kyamlgen` always loads the **strict** variant (D5). Rejecting an unknown field at
the point of entry is worth far more than accepting one.

### 5.2 Locating a kind's schema

The bundle names files `{kind}-{first-label-of-group}-{version}.json`, so
`networking.k8s.io/v1` collapses to `networking-v1` and the core group collapses to
plain `v1`. The naming is *almost* regular — the `meta.k8s.io` kinds are stored as
`apigroup-meta-v1.json` — so the derived name is only a fast path. The authoritative
answer comes from the **kind index** (D11): every file is read once for its
`x-kubernetes-group-version-kind` marker, giving a `(group, version, kind)` →
filename map. Scanning 635 files costs about 60 ms and is memoised.

### 5.3 `$ref` resolution

References inside the bundle take three forms, all of which resolve to the same
`$defs` table:

```
#/$defs/io.k8s.api.core.v1.Container
/api/_definitions.json#/$defs/io.k8s.api.core.v1.Container
https://kubernetes.io/api/_definitions.json#/$defs/io.k8s.api.core.v1.Container
```

`SchemaBundle.resolve()` follows a reference and merges any sibling keys (usually
`description`) over the resolved definition.

### 5.4 What the schema does *not* contain

Three gaps, each of which needed its own answer:

- **No enums.** Not one definition in the bundle has an `enum`. Permitted values
  exist only in prose. See §6.4 (D8).
- **No numeric bounds.** `port` has no `minimum`. See §6.5.
- **No required-ness for `ObjectMeta.name`.** The schema declares no required fields
  on `ObjectMeta` at all, but an object without a name cannot be created. See §6.6.

---

## 6. Form engine (`widgets.py`)

### 6.1 The widget tree

The engine turns a resolved schema node into a JSON widget tree:

```json
{
  "id": "w42",
  "name": "image",
  "path": ["spec", "template", "spec", "containers", "*", "image"],
  "kind": "string",
  "label": "Image",
  "description": "Container image name. More info: https://kubernetes.io/...",
  "required": true,
  "advanced": false
}
```

`kind` is one of `string`, `text`, `integer`, `number`, `boolean`, `select`,
`quantity`, `int-or-string`, `datetime`, `object`, `array`, `map` or `json`.

### 6.2 Schema → widget mapping

| Schema shape | Widget |
|---|---|
| `enum` present | `select` |
| `type: integer` / `number` | `integer` / `number`, with bounds where known |
| `type: boolean` | `boolean` |
| `type: string` | `string`, or `datetime` when `format: date-time` |
| `$ref` → `intstr.IntOrString` | `int-or-string` |
| `$ref` → `resource.Quantity` | `quantity` |
| object with `properties` | `object`, recursing into children |
| object with `additionalProperties: <schema>` | `map` — a key/value editor |
| object with `x-kubernetes-preserve-unknown-fields` | `json` |
| array of `$ref` | `array` with an item template |
| array of `string` | `array` of scalars |

`IntOrString` and `Quantity` are recognised by the definition they point at, not by
the inline `x-kubernetes-int-or-string` marker — that marker appears only twice in
the whole bundle.

### 6.3 The recursion guard

A `CustomResourceDefinition` embeds a `JSONSchemaProps`, which embeds another
`JSONSchemaProps`, and so on. The builder keeps a stack of the definition names
currently being expanded and falls back to a raw JSON editor when a definition
repeats. Without this, the walk never terminates.

### 6.4 Curated enums (D8)

Because the bundle carries no enum data, a curated table restores the permitted
values for the fields where a wrong value is rejected only by the API server:
`ServiceSpec.type`, `Container.imagePullPolicy`, `PodSpec.restartPolicy`,
`ContainerPort.protocol`, `HTTPIngressPath.pathType`, `PersistentVolumeClaimSpec.accessModes`,
and about twenty more. The values are rendered as a dropdown, so a typo becomes
impossible rather than merely detectable.

### 6.5 Curated bounds

Numeric ranges come from the API documentation rather than the schema: ports
1–65535, `nodePort` 30000–32767, `replicas` ≥ 0.

### 6.6 Required fields

A field is required when the schema says so, when a definition is in the
practically-required table (`Container.image`, `ServicePort.port`,
`IngressServiceBackend.name`), or when it is the top-level `metadata.name`.

### 6.7 Field visibility

A definition may name the properties that are shown by default; everything else is
folded into an "advanced" disclosure. This is an **allow-list** on purpose. The
Kubernetes schema keeps growing — v1.37 already carries alpha fields such as
`evictionResponders` and `hostnameOverride` — and a deny-list would surface every new
field to somebody who just wants to set an image.

### 6.8 Server-owned fields (D9)

Never offered: `status`, and the `ObjectMeta` fields the API server owns
(`uid`, `resourceVersion`, `creationTimestamp`, `managedFields`, `generation`,
`selfLink`, `deletionTimestamp`, `deletionGracePeriodSeconds`). `finalizers` and
`ownerReferences` are real authoring fields but are hidden behind "advanced".

---

## 7. Kind registry (`registry.py`)

The schema describes shape, not semantics. The registry supplies what the schema
cannot:

- **Scope** — namespaced or cluster-scoped.
- **Plural** — `Ingress` → `ingresses`, `NetworkPolicy` → `networkpolicies`, with
  irregulars in a table and regular rules (`s`/`x`/`ch`/`sh` → `+es`, consonant + `y`
  → `ies`) for the rest.
- **Ownership** — which controller normally creates this kind. `Pod` is normally
  created by a Deployment, `ReplicaSet` by a Deployment, `Node` by the kubelet.
  Authoring one means taking over that controller's job, which the form says so
  (R9).
- **Not authorable** — `Node`, `ComponentStatus`, the `*Review` kinds. A hand-written
  Node manifest is rejected in practice and teaches nothing.
- **Category** — for the kind picker.

---

## 8. Validation (D5)

Four layers, because each catches a class the others cannot.

| # | Layer | Catches | Needs a cluster? |
|---|---|---|---|
| 1 | Form-time (`validate.py`) | missing required fields, out-of-range ports, malformed names and labels, bad quantity syntax, invalid enum values | no |
| 2 | JSON Schema, strict variant | unknown fields, wrong types, invalid shapes | no |
| 3 | Semantic (`semantics.py`) | selector/label mismatches, `targetPort` matching no container port, dangling references, namespace ambiguity | no |
| 4 | Server dry-run | admission control, defaulting, real API-server rejection | **yes** (M4) |

### 8.1 A subtlety in the form-time layer

A missing object must not make its own required children look missing. `lifecycle`
is optional, and nothing inside it is required, so an absent `lifecycle` must not
produce *"Port is required"* from `lifecycle.preStop.tcpSocket.port`. The tree walk
therefore descends only into objects that are present, and treats a present-but-empty
object as genuinely incomplete.

### 8.2 A gap in the JSON Schema layer

Whether a top-level `spec` is required is **version-dependent**. The v1.37.0 schemas
mark it required, so a `Deployment` with no `spec` is rejected; the v1.31.0 and
v1.36.0 schemas do not, and the same manifest passes. This is a property of the
upstream schemas, not of the tool.

The tool enforces the rules of the version you selected, which is the right behaviour:
a manifest written for v1.31.0 should be judged by v1.31.0's rules. Layer 4 closes
the question definitively.

---

## 9. Semantic engine (`semantics.py`)

Rules that compare objects against each other. Errors are reserved for agreements
the API server itself would reject or that would silently break traffic; everything
else is a warning.

| Code | Rule | Level |
|---|---|---|
| `selector-template-mismatch` | A workload's `selector.matchLabels` must match its own pod template labels | error |
| `service-selector-unmatched` | A Service's selector must match a workload in the bundle | error |
| `service-empty-selector` | A Service with no selector routes to nothing | warning |
| `target-port-unmatched` | `targetPort` must match a container port, by number or by name | error |
| `ingress-backend-missing` | An Ingress backend must reference a Service in the bundle | error |
| `ingress-backend-port-missing` | …on a port that Service actually exposes | error |
| `scaler-target-missing` | An HPA must target a workload in the bundle | warning |
| `pdb-selector-unmatched` | A PodDisruptionBudget's selector must match the pods it protects | warning |
| `role-binding-ref-missing` | A RoleBinding's role and service account must exist | warning |
| `cluster-role-binding-ref-missing` | A ClusterRoleBinding's role and service account must exist | warning |
| `dangling-reference` | A referenced ConfigMap, Secret or PVC is not in the bundle | warning |
| `namespace-mismatch` | Objects in one bundle disagree about their namespace | warning |
| `image-no-tag` | An image has no tag, so it resolves to `:latest` | warning |
| `no-probe` | A long-running workload container has no health probe | warning |
| `limit-without-request` | Resource limits without requests | warning |

### 9.1 The bundle is not the cluster (D13)

Every rule above fires only when the bundle **contains** the relevant kind and none
of them matches. A reference that is simply absent from the bundle is not a
finding, because the object it names may already exist in the cluster.

```text
bundle has Services, none named "my-app"  →  error   (a real mismatch)
bundle has no Services at all               →  silent  (cannot know, and that is normal)
```

This is not a cosmetic rule. An earlier version warned "no workload is part of this
bundle" whenever a Service was generated on its own — which is the single most
common way to use the tool, and a warning that fires on correct input trains the
user to ignore warnings. The rule now matches the tool's own scope: it checks what
is in front of it, and says nothing about what it cannot see.

"Dangling" references to a ConfigMap, Secret or PVC stay warnings, because they
name an object the user is likely creating in the same session.

---

## 10. Presets (`presets/`)

A **preset** is a hand-written starting-point manifest for a kind. It is applied
automatically when the kind is opened, and it is what makes the form teach rather
than merely accept input.

### 10.1 A preset is a manifest, not a form definition

This is the decision the whole feature rests on (D12). A preset is a YAML file
containing a real Kubernetes manifest, and it is loaded, validated and rendered by
exactly the same code paths as anything the user produces.

The alternative — describing presets in some form-specific structure — would need a
second description of the API, and it would drift from the schema. A preset that is
a manifest cannot drift: if it stops being valid, the test that validates every
preset fails.

```
src/kyamlgen/presets/
  __init__.py           loader: preset_for(kind), curated_kinds(), is_curated(kind)
  curated/*.yaml        one hand-written manifest per kind
```

### 10.2 Which kinds have one, and how far they go

Seventeen kinds have a preset: Deployment, Service, ConfigMap, Secret, Ingress,
Namespace, StatefulSet, DaemonSet, Job, CronJob, PersistentVolumeClaim,
ServiceAccount, HorizontalPodAutoscaler, NetworkPolicy, ResourceQuota,
PodDisruptionBudget, Pod.

The rule for what goes in one is **the level people actually use**, not the level
the schema permits. The Deployment preset sets replicas, labels, the selector, one
container with a named port, resources with both requests and limits, and two
probes. It sets nothing else, and every field it does set is one the form shows
without opening the "advanced" disclosure.

The rest of the kinds have no preset and open empty. That is deliberate. A
generated skeleton for an obscure kind teaches less than a blank form with the
required fields called out, and it would fill the form with values the user has to
read carefully in order to recognise as fake.

### 10.3 The presets work together

The Deployment and Service presets are one design, not two. They share the label
`app: my-app`, and the Service's `targetPort` is the *name* of the container port
rather than a repeated number:

```yaml
# Deployment                        # Service
containers:                          selector:
  - ports:                             app: my-app
      - name: http                   ports:
        containerPort: 8080             - name: http
                                            port: 80
                                            targetPort: http
```

Adding both objects produces a bundle with **zero findings** — the selector
matches, the target port resolves, and no rule fires. The preset is therefore a
working demonstration of the coupling the tool exists to check, not just a filled-in
form. It also means the two ports cannot drift: renaming the container port keeps
the Service pointing at it.

### 10.4 Marking and clearing

A field is marked when its **current value still equals the preset's value at that
path**. Comparing values rather than tracking edits means the marker needs no state
of its own and survives an array being reordered. The marker is a live diff: every
field starts marked, and the moment the user types in one, that field loses its
mark.

Clearing is available at four granularities:

| Control | Scope |
|---|---|
| **×** beside a field | that one value |
| **Clear** in a section header | that whole subtree |
| **×** beside a map row | that key/value pair |
| **Remove** on an array item | that item |

And two toolbar actions on the active object: **Clear values** empties it, **Reset
to template** puts the preset back.

Clearing an object also has to drop that object's cached map rows. Otherwise the
rows reappear on the next render and put the values straight back — the same
class of bug as the renderer-creates-data one (§15.1).

---

## 11. Tutorials (`tutorials/`)

A tutorial is what makes the tool a teacher rather than a form. It has two
halves, and the split is the design.

### 11.1 The curated half — the judgement (D14)

Twenty-nine kinds have a hand-written tutorial: the seventeen that have a
template, plus the RBAC and scheduling kinds a course needs (Role, RoleBinding,
ClusterRole, ClusterRoleBinding, ReplicaSet, Endpoints, EndpointSlice,
LimitRange, ReplicationController, PriorityClass, StorageClass,
PersistentVolume).

They live in `tutorials/curated/<kind>.md` as Markdown, with YAML front matter
carrying the kind and a one-line summary:

```markdown
---
kind: Deployment
summary: Keeps N copies of your application running, and replaces them when you change the image.
---

A Deployment manages a ReplicaSet, which in turn manages Pods...

## Use it for
- A stateless service that should run several copies behind a [Service](...).

## Use something else for
- Workloads that need stable identities → [StatefulSet](...)
```

The curated half answers the questions only a person can answer: what the kind
is *for*, when to reach for something else, and the mistake that bites people.

### 11.2 The derived half — everything the tool already knows

The rest is generated, from the schema, the rule table and the registry:

| Section | Source |
|---|---|
| Summary | curated, or the schema's own description |
| **How it connects** | the relationship table in `semantics.py` |
| **What the tool checks for you** | the rule table — the rules' own summaries |
| **Worked example** | the template, where there is one |
| **Scope and ownership** | the registry — namespaced? who normally creates it? |

The other kinds get a **derived tutorial**: the schema's description, the scope,
the ownership advisory, the required fields, and the connections. A thin page,
but never an empty one.

### 11.3 Why the tutorial and the checker share their facts (D15)

The relationships and the checks come from the same tables the semantic engine
uses, so the tutorial cannot describe a check that does not exist or a connection
that is not checked.

That distinction is sharper than it first looks, and getting it wrong is what
the first implementation did. **"Which kinds relate to each other" and "which
checks apply to this kind" are different questions.** A rule table entry says
`image-no-tag` concerns a Deployment — but a Deployment does not *connect* to a
CronJob because of it. So there are two tables:

- `RULES` — which kinds a check applies to, and what it checks. Drives "What the
  tool checks for you".
- `RELATIONSHIPS` — which kinds reference each other, directionally, and the
  check that catches a mismatch. Drives "How it connects".

The relationships are directional because the counterpart set depends on which
side you are reading from: for a Deployment the counterpart of the ConfigMap
relationship is `ConfigMap`; for a ConfigMap it is the kinds that can reference
it. Peers are never counterparts — a Deployment does not connect to a
StatefulSet.

A test asserts that every relationship names a real rule, and that the rule
covers both sides.

### 11.4 The tutorial is wired into the form

The panel sits above the form, expanded by default, with the derived sections
collapsed. Two kinds of link make it one surface rather than a page beside a
form:

- **Related kinds** are ordinary links to their own forms.
- **Field paths** are links that scroll the form to that field and flash it —
  `spec.selector.matchLabels` in the prose, the actual input in the form.

A path in a tutorial is written the way it would be spoken, with `[]` for array
items: `spec.ports[].port`. A test walks the widget tree and the tutorial
together, so a typo is a failing test rather than a dead link.

---

## 12. Quizzes (`quizzes/`)

A quiz is what turns a tutorial into something you can be *wrong* about. Reading
about the selector drift teaches you less than being asked what happens when it
drifts and having to answer.

### 12.1 The shape of a question (D16)

Questions are structured data, not prose, because a quiz has to be scored:

```yaml
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
      The selector is how the Deployment says which Pods are its own. If it
      matches nothing, it creates a ReplicaSet that adopts no Pods — and the
      pods it does create still report as Running, because nothing is wrong
      with them.
```

The `why` is **required**. A question without an explanation is a test, not a
teaching aid — and the explanation is where the learning actually happens.

### 12.2 Two tiers, again

**Curated** — twenty-nine kinds, six to eight questions each: **206 questions**.
Every one targets a misconception or a silent failure, not a field name. The
Deployment's selector drift; why a Service should target a *named* port; why
`restartPolicy: Always` is rejected in a Job; what `targetPort` actually resolves
to; why a RoleBinding with a missing role is accepted and grants nothing.

**Derived** — every other kind, one to three questions generated from what the
tool already knows:

| Derived question | Available for |
|---|---|
| "Which of these is cluster-scoped?" | all 213 |
| "Which of these fields is required?" | 146 kinds |
| "Which of these is a valid value for `<field>`?" | 90 kinds |

The derived tier is recall rather than understanding, and for a `*List` kind the
enum question degenerates into `items.*.apiVersion`. It exists so that no kind
opens with nothing. The curated quizzes are where the teaching is.

### 12.3 The interaction

The questions are rendered by the server; the JavaScript only handles the reveal.
Choosing an option marks that question, shows its verdict and explanation, and —
if the answer was wrong — also marks the right one. A running score appears, and
a summary when every question is answered.

Real `<input type="radio">` elements, so keyboard navigation and screen readers
work without any extra work.

**Options are shuffled server-side.** A quiz whose answer is always in the same
place teaches the position rather than the material. The explanations are written
to be position-independent so the shuffle does not break them.

### 12.4 The quiz is checked as carefully as the tutorial

- Every question is validated on load: the answer index must be in range, the
  options must be unique and non-empty, and the explanation must not be empty.
- Every field path and kind link in an explanation must resolve, exactly as in
  the tutorials.
- No two questions in a quiz may be the same, and the answer must not always be
  in the same position.
- The derived generator must produce valid questions for all 213 kinds.

---

## 13. Renderer (`render.py`)

### 10.1 Key order (D6)

The schemas list properties alphabetically, which produces `image` before `name`
inside a container. The renderer applies a preference list so the output reads the
way manifests are conventionally written. User-keyed maps — `ConfigMap.data`,
`metadata.labels`, `metadata.annotations` — keep the user's own ordering.

### 10.2 String quoting (D6)

Kubernetes parses YAML through go-yaml v2, which follows YAML 1.1, where a bare
`on`, `yes` or `no` is a boolean. A ConfigMap value of `on` written unquoted arrives
in the pod as `true`.

PyYAML's 1.1 resolver quotes such strings automatically (`feature: 'on'`).
`ruamel.yaml` in 1.2 mode would not, and would silently corrupt the value. This is
the whole reason the project uses PyYAML, and it is covered by a test.

### 10.3 Pruning

Empty strings, empty lists, empty maps and empty objects are removed so the YAML
contains only what the user filled in. Validation still runs against the *unpruned*
object, so a required field that was never touched is still reported.

---

## 14. Web application (`app.py`)

| Route | Purpose |
|---|---|
| `GET /` | Kind picker, grouped by category, searchable |
| `GET /form?apiVersion=&kind=` | The workbench |
| `GET /api/kinds` | The kind catalogue |
| `GET /api/presets` | The kinds that have a hand-written preset |
| `GET /api/tree` | The widget tree for a kind, plus its preset |
| `POST /api/render` | Validate a bundle of objects and return YAML plus issues |
| `POST /api/validate` | Validate pasted YAML and re-render it canonically |
| `GET /healthz` | Liveness |

The workbench holds a list of objects, so a Deployment and its Service are generated
together and checked against each other. The output pane shows the YAML and every
issue, tagged with the object it belongs to.

### 11.1 Why the form is rendered by JavaScript (D10)

The widget tree is JSON, and the browser has it. Rendering the form from the tree in
JavaScript means there is exactly one implementation of the widget rules. A
server-rendered form would need a second implementation of the same rules in Jinja,
and the two would drift.

The cost is that the form needs JavaScript. For a local developer tool that is the
right trade.

---

## 15. Module layout

```
src/kyamlgen/
  schemas.py     schema bundle access, kind index, $ref resolution
  widgets.py     schema → widget tree, curated overlays
  registry.py    scope, plural, ownership, categories
  validate.py    form-time checks, JSON Schema validation
  semantics.py   cross-object rules
  render.py      pruning, key ordering, YAML output
  presets/       hand-written starting-point manifests (§10)
    __init__.py  loader
    curated/     one YAML manifest per kind
  tutorials/     the teaching content (§11)
    __init__.py  loader and assembly
    curated/     one Markdown file per kind
  quizzes/       the self-test content (§12)
    __init__.py  loader, derived generator, HTML rendering
    curated/     one YAML file per kind
  app.py         FastAPI routes
  cli.py         serve / kinds / presets / preset / tutorial / quiz / tree / generate / validate
  templates/     base.html, index.html, form.html
  static/
    style.css    the whole stylesheet
    formstate.js pure data-path logic, shared by the browser and the Node tests
    quiz.js      the quiz reveal and scoring
    app.js       renders the form from the widget tree
    picker.js    renders the kind catalogue
tests/
  test_schemas.py    bundle layout, file naming, $ref resolution, kind index
  test_widgets.py    widget mapping, required fields, visibility, recursion guard
  test_validation.py form-time checks, schema validation, every semantic rule
  test_render.py     key ordering, YAML 1.1 quoting, pruning, multi-document output
  test_presets.py    every preset validates; presets use only common fields
  test_tutorials.py  every tutorial's links resolve; every kind has a tutorial
  test_quizzes.py    every quiz is well formed; every kind has a quiz
  test_api.py        end-to-end HTTP behaviour
  test_javascript.py runs the Node tests below
  js/formstate.test.js  the form's path arithmetic, under `node --test`
```

### 13.1 Why the form's data logic is a separate file

Every bug found while building the form lived in the path arithmetic — the code that
decides where in the nested object a value belongs — and not in the DOM code. One of
them was the worst kind: the renderer created the intermediate objects it walked
through, so every advanced field it merely *displayed* appeared in the submitted data
as an empty object, and the server duly reported the missing required fields inside
them as real errors. The user saw twenty phantom problems on an empty form.

`formstate.js` holds that arithmetic and nothing else, so it can be tested without a
browser. `node --test tests/js/` runs those tests, and `test_javascript.py` runs them
from pytest, so `uv run pytest` still covers the whole project.

---

## 16. Status and milestones

| Milestone | Scope | Status |
|---|---|---|
| M0 | Repo skeleton, schema service, kind registry, vertical slice | **done** |
| M1 | Generic form engine: widget mapping, fragments, arrays, maps, quantity and int-or-string widgets | **done** |
| M2 | Semantic engine, cross-object checks, multi-object bundles | **done** (bundles and semantics); shared-value propagation still to do |
| M3 | Four-layer validation surfaced inline; raw-YAML mode for every kind | **partial** — layers 1–3 done, raw-YAML paste mode done, per-kind raw editor not done |
| M4 | Apply service (`kubectl --dry-run=server`, then apply) | **not started** — needs a local cluster (`kind`); Docker is already installed |
| M5 | Ownership advisories, manifest library, Kustomize export | **partial** — advisories and presets done; library and Kustomize export not started |
| — | Curated presets for seventeen kinds, with per-field and per-section clearing | **done** (§10) |
| — | Curated tutorials for twenty-nine kinds, derived tutorials for the rest | **done** (§11) |
| — | Curated quizzes for twenty-nine kinds (206 questions), derived quizzes for the rest | **done** (§12) |

---

## 17. Open questions

1. **Shared-value propagation.** The bundle model lets a Deployment and a Service be
   generated together, but the labels and ports are still typed twice. Should
   selecting a Service from a Deployment pre-fill its selector and ports from the
   Deployment's template? This is the remaining half of the coupling story.
2. **Server dry-run.** M4 needs a cluster. `kind` is the cheapest path on this
   machine — Docker is installed and the image is about a gigabyte. Should the
   tool require a cluster for M4 to count as done, or is a graceful "no cluster
   reachable" acceptable?
3. **Kustomize export.** `kubectl` here already bundles kustomize v5.8.1. Emitting a
   `kustomization.yaml` alongside the generated manifests would make the output
   composable. Worth doing in M5?
4. **Which Kubernetes version is the default?** The tool currently defaults to the
   newest in the bundle (v1.37.0) while the installed `kubectl` is v1.36.1.
   Defaulting to the client's version would need a cluster to detect.
