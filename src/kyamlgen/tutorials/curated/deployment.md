---
kind: Deployment
summary: Keeps N copies of your application running, and replaces them when you change the image.
---

A Deployment manages a ReplicaSet, which in turn manages Pods. You describe the
state you want — three copies, this image — and Kubernetes makes it true, then
keeps it true. If a pod dies, another appears. If you change the image, the old
ones are replaced a few at a time.

The Deployment is the reason Kubernetes is usable at all. Once you describe a
*desired state* instead of a *procedure*, everything else — restarts, rollouts,
scaling, self-healing — falls out of the same mechanism.

## Use it for

- A stateless service that should run several copies behind a
  [Service](/form?apiVersion=v1&kind=Service).
- Anything that should be rolled out gradually without dropping traffic.

## Use something else for

- Workloads that need stable identities or per-replica storage →
  [StatefulSet](/form?apiVersion=apps/v1&kind=StatefulSet)
- One-off tasks that run to completion → [Job](/form?apiVersion=batch/v1&kind=Job)
- Something that must run on every node → [DaemonSet](/form?apiVersion=apps/v1&kind=DaemonSet)
- A single debugging pod → [Pod](/form?apiVersion=v1&kind=Pod)

## Watch out for

The same label has to appear in three places, and the first two are easy to get
wrong:

- [spec.selector.matchLabels](field:spec.selector.matchLabels) says which pods this
  Deployment manages.
- [spec.template.metadata.labels](field:spec.template.metadata.labels) says what
  labels it actually puts on them.

A Deployment whose selector does not match its own template manages **zero** pods
— and still reports them as Running, because the pods exist and the pods are fine.
The mismatch is between two fields in the same object, so no schema check catches
it.

The third place is a different object: a [Service](/form?apiVersion=v1&kind=Service)
picks up your pods by their labels, so its `spec.selector` has to match too. That
one is not in the same file unless you put it there, which is why it slips through
review most often.
