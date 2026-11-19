we know nobody like kubernetes yaml files to be written by hand from scratch
it will be a good idea if we can get a webform where we feed values like pd name, servive metadata , selector port targetport etc for kubernetes primitive objects like
deployments, pods , services, replicasets, nodes etc
and once we submit the form we get yaml which we can copy and paste into yaml files and use these yaml files for creating applying on kubernetes cluster

---

# Decision Log

> Append-only. Newest entries at the bottom.
> Each entry records what was asked, what was decided, **why**, and which section of
> `architecture.md` it justifies. See `architecture.md` §3 for the decision index.

---

## 2026-11-19 — Project brief

**Asked:** A web form where you feed values — pod name, service metadata, selector,
port, target port — for Kubernetes primitive objects (deployments, pods, services,
replicasets, nodes), and get YAML back that you can copy-paste and apply to a
cluster.

**Decided:** Capture the brief as requirements R1–R10 in `architecture.md` §2. Before
designing anything, split the problem in two: the *knowledge* problem (which fields
exist, what types they have, which are required) and the *coupling* problem (the same
value has to appear in several places, and the places drift silently).

**Why:** The brief describes one problem, but there are two with different solutions.
The knowledge problem is a lookup that a machine can answer perfectly. The coupling
problem is the one that actually bites: a Deployment with a typo in
`spec.selector.matchLabels` deploys perfectly, serves zero traffic, and looks correct
in review. Any design that only solves the first problem is an IDE with a form
bolted on.

**Affects:** `architecture.md` §1, §2

---

## 2026-11-19 — Scope decisions

**Asked:** Three questions: how should the forms be produced; how should the tool be
delivered; and which kinds should be in the first working version.

**Decided:**

1. **Hybrid** — forms generated from the Kubernetes schema, with curated layouts for
   the kinds people actually author. Every other kind gets a generic schema-driven
   form.
2. **A local FastAPI server**, with a server-rendered shell and a JavaScript form
   renderer.
3. **Every kind in the bundle**, including the controller-owned ones (Pod,
   ReplicaSet, Node) and the ones nobody hand-writes.

**Why:**

1. *Hybrid.* The schema is the only complete and always-correct description of the
   API surface, and it is machine-readable. Hand-writing forms guarantees that some
   field is missing or misnamed. But a generic auto-form for `PodSpec` is a
   kilometre-long scroll, so the handful of kinds that get typed constantly still
   deserve a curated layout. The split falls where the frequency is.
2. *Local server.* The tool's value is in the validation and the coupling rules, all
   of which live server-side. A browser-only app could not run the semantic engine
   over a bundle of objects without reimplementing it in JavaScript, and a hosted
   service would be a second thing to deploy and pay for.
3. *Every kind.* The generic engine makes coverage free — 193 distinct kinds across
   13 Kubernetes versions — so excluding any of them would be an arbitrary limit.
   The controller-owned kinds are included *with an advisory*, because that advisory
   is more valuable than the exclusion: it is the moment the user learns that
   authoring a Pod by hand means taking over a controller's job.

**Affects:** `architecture.md` §1, §6, §7, §12

---

## 2026-11-19 — Form source: the bundled Kubernetes schema

**Asked:** Where does the form's field list come from?

**Decided:** The OpenAPI schemas bundled with `kubernetes-validate`, loaded from the
installed package. The **strict** variant is always used: `additionalProperties:
false` on 622 of the 635 definitions.

**Why:** The bundle is a faithful copy of the upstream Kubernetes OpenAPI schemas
covering v1.25.0 through v1.37.0, and it installs with `uv sync` — no network at
runtime, no cluster, no API discovery. That satisfies the offline requirement and
makes the tool's correctness independent of which cluster happens to be reachable.

The strict variant matters more than it sounds. A permissive schema accepts
`spec.conatiners` as if it were `spec.containers`, and the mistake surfaces minutes
later as a pod that will not start. Rejecting it in the form is worth far more than
accepting it.

One consequence to record: the bundle is *not* a full OpenAPI document. It is a
curated subset — the schemas for the resources, not the discovery information. So
`kubectl explain` needs a cluster and `kyamlgen` does not.

**Affects:** `architecture.md` §5

---

## 2026-11-19 — The bundle's file naming is irregular (D11)

**Asked:** (implicit) How is a kind's schema file located?

**Decided:** The file name is derived from the API group — `{kind}-{first label of
the group}-{version}.json`, so `networking.k8s.io/v1` collapses to `networking-v1` —
but the derived name is only a fast path. The authoritative lookup is a **kind index**
built by reading each file's `x-kubernetes-group-version-kind` marker.

**Why:** The derivation is right almost always and wrong in a way that is easy to
miss. The `meta.k8s.io` kinds are stored as `apigroup-meta-v1.json`, not
`apigroup-v1.json`, and the first implementation looked for the derived name and
simply did not find the schema for 24 of the 193 kinds. The failure was silent
rather than loud: the kind appeared in the catalogue and then blew up when you
tried to open it.

The index fixes the class of bug rather than the instance. Scanning 635 files costs
about 60 ms, which is free at startup and memoised thereafter.

**Affects:** `architecture.md` §5.2

---

## 2026-11-19 — The schema carries no enum data (D8)

**Asked:** (implicit) The `ServiceSpec.type` field renders as free text. Why?

**Decided:** Curate the permitted values by hand, in a table keyed by
(definition, property), and render them as a dropdown.

**Why:** The bundle contains **not a single `enum`** across all 635 definitions.
Permitted values live only in the prose of the field descriptions. So `type:
ClustrIP` is a perfectly valid string as far as every schema check is concerned,
and it is rejected by the API server at apply time — by which point the user has
moved on to something else.

This is a genuine gap in the upstream schema, not a bug in the tool, and no amount of
schema-driven generation can close it. It has to be curated. The table covers the
fields where a wrong value is caught only by the API server: `ServiceSpec.type`,
`Container.imagePullPolicy`, `PodSpec.restartPolicy`, `ContainerPort.protocol`,
`HTTPIngressPath.pathType`, `PersistentVolumeClaimSpec.accessModes`, and about
twenty more.

The same reasoning applies to numeric bounds, which the schema also omits: ports are
1–65535, `nodePort` is 30000–32767, and these come from the API documentation.

**Affects:** `architecture.md` §5.4, §6.4, §6.5

---

## 2026-11-19 — Server-owned fields are never offered (D9)

**Asked:** (implicit) Should the form show `status`?

**Decided:** No. `status` is excluded, and so are the `ObjectMeta` fields the API
server owns: `uid`, `resourceVersion`, `creationTimestamp`, `managedFields`,
`generation`, `selfLink`, `deletionTimestamp`, `deletionGracePeriodSeconds`.

**Why:** `status` appears on 45 of the 161 kinds in a version and is a subresource —
the API server owns it, and a value in the manifest is either ignored or rejected
depending on the resource. Offering it teaches the wrong thing about who owns what.
The `ObjectMeta` fields are the same story: they are set by the API server at
creation time, and a hand-written value for them is either ignored or causes a
conflict.

`finalizers` and `ownerReferences` are different — they are genuinely authorable —
so they stay, hidden behind "advanced".

**Affects:** `architecture.md` §6.8

---

## 2026-11-19 — Field visibility is an allow-list

**Asked:** (implicit) How do you decide which of the 200-odd fields in a `PodSpec`
to show?

**Decided:** Each definition names the properties shown by default; everything else
is folded into an "advanced" disclosure. Definitions with no entry show everything.

**Why:** The Kubernetes schema keeps growing. v1.37 already carries alpha fields like
`evictionResponders` and `hostnameOverride`. A deny-list — "hide these known-unusual
fields" — would surface every new field to somebody who just wants to set an image,
and the deny-list would need updating with every Kubernetes release.

An allow-list inverts that: a new field is hidden by default, which is the safe
default, and adding it to the visible set is a deliberate act. The cost is that a
field nobody thought of stays hidden; the benefit is that the form does not get
worse with every release.

**Affects:** `architecture.md` §6.7

---

## 2026-11-19 — The form is rendered by JavaScript (D10)

**Asked:** (implicit) Server-rendered Jinja form, or client-side rendering?

**Decided:** The server renders the page shell and the widget tree as JSON.
JavaScript renders the form from the tree.

**Why:** The widget tree *is* the form's data model, and the browser already has it.
Rendering the form from it in JavaScript means there is exactly one implementation
of the widget rules. A Jinja renderer would need a second implementation of the same
rules, and two implementations of the same rules drift — one gets a fix, the other
does not, and the bug appears only in one of them.

The cost is that the form requires JavaScript. For a local developer tool that is the
right trade. The CLI covers the no-browser case with the same validation.

**Affects:** `architecture.md` §13.1

---

## 2026-11-19 — YAML rendering with PyYAML, not ruamel.yaml (D6)

**Asked:** (implicit) Which YAML library?

**Decided:** PyYAML.

**Why:** Kubernetes parses YAML through go-yaml v2, which follows YAML 1.1, where a
bare `on`, `yes` or `no` is a **boolean**. A ConfigMap value of `on` written
unquoted arrives in the pod as `true` — a silent data corruption that looks like a
bug in the application.

PyYAML's 1.1 resolver quotes such strings automatically (`feature: 'on'`).
`ruamel.yaml` in its default 1.2 mode would *not*, because YAML 1.2 dropped the
`yes`/`no` booleans. Choosing ruamel for its nicer round-tripping would have
introduced exactly this bug, and it is covered by a test that round-trips `on`,
`yes` and `80` through the renderer and back.

The renderer also applies a key preference list, because the schemas list properties
alphabetically and `image` before `name` inside a container reads wrong.

**Affects:** `architecture.md` §12

---

## 2026-11-19 — Four validation layers (D5)

**Asked:** (implicit) What does "validate" mean here?

**Decided:** Four layers, each catching a class the others cannot: form-time checks
driven by the widget tree, JSON Schema validation against the strict variant, the
cross-object semantic rules, and — in M4 — a real API server dry-run.

**Why:** Each layer has a blind spot that the next one covers.

The form-time layer knows about required fields, numeric ranges, name formats and
enums, but it only sees what the form knows about. The schema layer knows the exact
shape of every field, but it sees one object at a time and carries no enums. The
semantic layer sees the whole bundle and knows that a selector has to match a
template, but it cannot know that a field is the wrong type. And all three are
approximations: the schema does not even mark a top-level `spec` as required, so a
`Deployment` with no `spec` passes all of them.

Only a real API server catches what the approximations miss. That is M4, and it is
the one milestone that needs a cluster.

**Affects:** `architecture.md` §8

---

## 2026-11-19 — The semantic engine is a separate layer, not string substitution (D7)

**Asked:** (implicit) How is the coupling between objects handled?

**Decided:** A semantic engine with named rules that analyse the whole bundle and
emit typed issues. Not template variables, not text substitution.

**Why:** The tempting shortcut is to have one "labels" field that gets written into
several places in the output. That works right up until it does not: it cannot
express "this Service's selector must match *some* workload's labels", it cannot
distinguish a real mismatch from a rule that was never checked, and it produces
YAML with no way to explain why it is the way it is.

Rules with names and severities can be tested individually, can be explained to the
user, and can be extended. The first cut has fourteen of them
(`architecture.md` §9), and each one corresponds to a way a hand-written manifest
silently breaks.

The severity split is deliberate. Errors are reserved for agreements the API server
would reject or that would silently break traffic — a selector that matches nothing,
a `targetPort` matching no container port. Everything else is a warning, including
"this ConfigMap is not in the bundle", because the referenced object may well
already exist in the cluster. The tool can only see the bundle, and pretending
otherwise would make it wrong.

**Affects:** `architecture.md` §9

---

## 2026-11-19 — Bundles, not single objects

**Asked:** (implicit) Should the tool generate one object or several?

**Decided:** The workbench holds a *list* of objects. A Deployment and its Service
are generated together, in one multi-document YAML file, and checked against each
other.

**Why:** The coupling rules are only meaningful across objects. Checking a Service
against a Deployment that is not in the same bundle can only produce "cannot
verify" warnings, which is exactly the case the tool most needs to help with — the
Deployment and the Service you just wrote.

This also matches how manifests are actually applied: `kubectl apply -f` on a
multi-document file is the normal case, and it is atomic per object, not per file.

**Affects:** `architecture.md` §9, §13

---

## 2026-11-19 — Correction: whether `spec` is required is version-dependent

**Asked:** (implicit, found while checking the browser output) The workbench reported
two errors for an empty Deployment: *"Spec is required."* from the form-time layer and
*"Missing required field: 'spec'"* from the schema layer. The schema layer was not
supposed to catch that — the earlier entry in this log states that the schemas do
not mark a top-level `spec` as required.

**Decided:** The earlier claim was too broad, and is corrected here. The requirement
**is** version-dependent: the v1.37.0 schemas mark `spec` required at the top level;
the v1.31.0 and v1.36.0 schemas do not, and the same spec-less `Deployment` passes
schema validation there. The tool enforces the rules of the version the user selected,
which is the correct behaviour — a manifest written for v1.31.0 should be judged by
v1.31.0's rules.

**Why:** This was verified directly against all three schema versions rather than
inferred. The general point stands and is worth keeping: the upstream schemas are
not uniform across versions, so a rule that holds for one Kubernetes version is not
safe to assume for another. It is also the second time the same schema bundle has
surprised us — the first was the absence of enums, the second the irregular file
naming — and both times the surprise came from the bundle not being as uniform as
the API documentation implies.

**Affects:** `architecture.md` §8.2

---

## 2026-11-19 — Documentation conventions

**Asked:** (implicit) How should the design be recorded?

**Decided:** Two documents, mirroring the convention already established in the
ServiceNow doc-search project: `architecture.md` is the design of record and
`INTENT.md` is this append-only log. Every decision gets an `D#` in
`architecture.md` §3 and a dated entry here.

**Why:** The value of the log is that it records what was *asked* and what was
*decided and why*, separately from the design. A design document that carries its
own rationale grows unreadable, and a log that carries design detail goes stale.
Cross-referencing the two makes the lookup work in both directions.

**Affects:** `architecture.md` §3, `architecture.md` preamble

---

## 2026-11-19 — Presets: hand-written manifests for seventeen kinds

**Asked:** "We should have some default templates pre filled and a button to clean
default values in single shot or deleting individual values with single click.
Default templates help user in thinking clearly. While filling default values no
need to make a very exhaustive template — instead have templated filled only to that
level which people usually use."

**Decided:** Seventeen kinds get a hand-written preset, applied automatically when
the kind is opened. A preset is a **real YAML manifest**, not a form definition.
The kinds are Deployment, Service, ConfigMap, Secret, Ingress, Namespace,
StatefulSet, DaemonSet, Job, CronJob, PersistentVolumeClaim, ServiceAccount,
HorizontalPodAutoscaler, NetworkPolicy, ResourceQuota, PodDisruptionBudget and Pod.

Clearing is available at four granularities: a **×** on a field, a **Clear** on a
section, a **×** on a map row, a **Remove** on an array item — plus **Clear values**
and **Reset to template** for the whole object. A field is marked with a dot while
it still holds the preset's value.

**Why:**

1. *A preset is a manifest.* This is the decision the feature rests on. If a preset
   were described in some form-specific structure, it would be a second description
   of the Kubernetes API — and it would drift from the schema, silently, the way
   hand-written documentation drifts. As a manifest, a preset is loaded, validated
   and rendered by exactly the same code as anything the user produces, and it
   cannot drift: if it stops being valid, the test that validates every preset
   fails. The schema stays the single source of truth.

2. *Seventeen, hand-written, and no generator.* "All kinds" was the first ask, and
   the honest answer was that a *generated* skeleton teaches less than a blank form
   with the required fields called out — and it fills the form with values the user
   has to read carefully to recognise as fake. A hand-written example teaches the
   shape of a good manifest, which is the whole point. The other ~196 kinds open
   empty, and that is a deliberate silence rather than a gap.

3. *"Only to that level which people usually use."* The Deployment preset sets
   replicas, labels, the selector, one container with a named port, resources with
   both requests and limits, and two probes. Not a single field that the form hides
   behind "advanced" — and that is enforced by a test that walks the widget tree
   and the preset together, so a future edit to a preset cannot quietly start
   setting fields the user cannot see.

4. *Marking by value, not by tracking edits.* A field is marked when its current
   value still equals the preset's value at that path. The alternative — recording
   which fields the user has touched — needs state that has to be kept in step with
   array insertions and removals. Comparing values needs no state at all, survives
   reordering, and turns the marker into a live diff: every field starts marked,
   and the moment the user types in one, that field loses its mark.

5. *The Deployment and Service presets are one design.* They share the label
   `app: my-app`, and the Service's `targetPort` is the *name* of the container
   port rather than a repeated number. Adding both produces a bundle with zero
   findings, which makes the preset a working demonstration of the coupling the
   tool exists to check — and means the two ports cannot drift apart.

**Affects:** `architecture.md` §10, §3 (D12)

---

## 2026-11-19 — The bundle is not the cluster

**Asked:** (implicit, found while building the presets) Opening the Service preset
on its own produced a warning: *"Service my-app selects app=my-app but no workload
is part of this bundle, so the match cannot be checked here."* The same shape of
warning fired for an Ingress with no Service in the bundle, and for an HPA whose
target was not in the bundle.

**Decided:** Removed the three "unverifiable" rules. A cross-object rule now fires
only when the bundle **contains** the relevant kind and none of it matches. A
reference that is simply absent from the bundle is not a finding.

**Why:** These rules were wrong, not merely noisy. The bundle is not the cluster: a
Service applied on its own may well route to a Deployment that already exists, and
an HPA may well scale a workload that was applied in an earlier command. Treating
absence as suspicious means warning about correct input — and **a warning that
fires on correct input trains the user to ignore warnings**, which destroys the
value of the rules that matter.

The rule that survives is the useful one: when the bundle *does* contain Services
and none is named `my-app`, that is a real mismatch and it is still an error. The
tool checks what is in front of it and says nothing about what it cannot see.

The `dangling-reference` rule stays a warning, because a ConfigMap or Secret
referenced by a workload is exactly the kind of object the user is creating in the
same session, and the warning disappears once they add it.

**Affects:** `architecture.md` §9.1, §3 (D13)

---

## 2026-11-19 — Tutorials for every kind

**Asked:** "This application will be used in teaching Kubernetes to people. Let's
accompany each kind to have a tutorial."

**Decided:** Every kind gets a tutorial, in two tiers. Twenty-nine kinds have a
hand-written one, in Markdown at `tutorials/curated/<kind>.md`; the rest get a
**derived** one assembled from the schema, the rule table and the kind registry.

The tutorial panel sits above the form, expanded by default, with the derived
sections collapsed. Related kinds are links to their forms, and field paths in the
prose are links that scroll the form to that field and flash it.

**Why:**

1. *The form already shows every field with the API's own description.* So the
   tutorial's unique value is the judgement: what the kind is **for**, when to
   reach for something else instead, and how it couples to other kinds. Writing a
   tutorial that repeated the field descriptions would have been work and no
   teaching.

2. *Markdown, and the tutorial is prose.* A tutorial is prose, and prose belongs in
   a prose file. YAML block scalars are a workaround, and a teacher editing
   `deployment.md` in a text editor is a workflow that will actually happen. The
   cost is one small pure-Python dependency.

3. *Twenty-nine, not all 213.* "Each kind" is honoured by the derived tier — no
   kind opens with nothing — but a *hand-written* tutorial for every kind would
   be uneven across a course. The set chosen is the one a Kubernetes course
   actually walks: the workload, networking, configuration, storage, scaling and
   access-control kinds. RBAC was the gap worth closing; without Role and
   RoleBinding a course has a hole in it.

4. *A derived tier beats nothing.* For the other 184 kinds the tutorial is the
   schema's own description, the scope, the ownership advisory, the required
   fields and the connections. It is thin, and it is honest — it says what the
   API server demands and who normally creates the object, which is the first two
   things you want to know.

**Affects:** `architecture.md` §11, §3 (D14)

---

## 2026-11-19 — The tutorial and the checker share their tables

**Asked:** (implicit, found while building the tutorial) The first implementation
derived the "how it connects" section from the rule table, and produced
nonsense: a Deployment appeared to "connect" to CronJob, DaemonSet, Job, Pod,
ReplicaSet and StatefulSet, because those are the kinds the `image-no-tag` rule
applies to.

**Decided:** Two tables instead of one. `RULES` says which kinds a *check* applies
to and what it checks. `RELATIONSHIPS` says which kinds *reference each other*,
directionally, and which check catches a mismatch.

**Why:** "Which kinds relate to each other" and "which checks apply to this kind"
are different questions, and the first implementation conflated them. A Deployment
does not connect to a CronJob because both of them can have an untagged image.

The relationships have to be *directional* for the same reason. For a Deployment,
the counterpart of the ConfigMap relationship is `ConfigMap`. For a ConfigMap, it
is the kinds that can reference it. One symmetric set cannot produce both, and
peers must never be listed as counterparts — a Deployment does not connect to a
StatefulSet.

The relationship table is also where the last two gaps in the checker came from.
Writing "a RoleBinding grants a role to a subject, so both have to exist" and
"a PodDisruptionBudget selects the pods it protects" made it obvious that the tool
checked neither. Both are now rules.

**Affects:** `architecture.md` §9, §11.3, §3 (D15)
