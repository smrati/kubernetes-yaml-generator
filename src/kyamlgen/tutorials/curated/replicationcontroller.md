---
kind: ReplicationController
summary: The original way to keep Pods running — kept for compatibility, not for new work.
---

A ReplicationController keeps a stated number of Pods running with identical
labels. It is the original version of what a
[ReplicaSet](/form?apiVersion=apps/v1&kind=ReplicaSet) does, and it predates the
`apps/v1` API group entirely.

Nothing creates it for you any more. There is no reason to use it in new
manifests.

## Use it for

- Very old automation that still speaks `v1`.

## Use something else for

- Almost always → [Deployment](/form?apiVersion=apps/v1&kind=Deployment), which
  adds rolling updates and a revision history on top of the same behaviour.
- Keeping Pods alive with no rollout behaviour at all →
  [ReplicaSet](/form?apiVersion=apps/v1&kind=ReplicaSet)

## Watch out for

Its one real difference from a ReplicaSet is that it selects Pods by
`spec.selector` alone — there is no `matchLabels`/`matchExpressions` split, and
no way to select on anything other than equality. A ReplicaSet can select with
set-based requirements; a ReplicationController cannot.

If you find one in a cluster, it is usually because something migrated from
`extensions/v1beta1` and never got updated.
