---
kind: StatefulSet
summary: Like a Deployment, but the Pods keep their names and their own storage.
---

A StatefulSet is a [Deployment](/form?apiVersion=apps/v1&kind=Deployment) with two
differences that matter: the Pods keep stable identities (`my-app-0`, `my-app-1`,
`my-app-2`), and each Pod gets its own volume from a template.

That gives you the two things a Deployment cannot do:

- **Stable identity.** The Pod named `my-app-2` is always the same Pod, with the
  same name, the same hostname, and the same storage. It can find its peers, and
  it can be written to by name.
- **Per-replica storage.** Each Pod gets a separate PersistentVolumeClaim, so
  deleting one Pod does not delete another's data.

## Use it for

- A database, or anything with per-instance identity.
- A system where a replica must know which one it is — a broker, a shard, a
  leader.

## Use something else for

- A stateless service → [Deployment](/form?apiVersion=apps/v1&kind=Deployment).
  If your app does not care which replica it is, a StatefulSet buys you nothing
  and costs you ordering constraints.
- A task → [Job](/form?apiVersion=batch/v1&kind=Job)

## Watch out for

A StatefulSet is not faster or more available than a Deployment. It is *more
particular*, and the particularity has costs: Pods start and stop in order, and
the last Pod will not start until the previous one is ready. That ordering is
what makes a StatefulSet wrong for a stateless service — a slow-starting replica
blocks the ones behind it.

Also note `spec.serviceName`. It is the Service that gives the Pods their stable
DNS names, and the StatefulSet expects it to exist. The StatefulSet does not
create it.
