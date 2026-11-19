---
kind: ReplicaSet
summary: The thing a Deployment actually manages — a set of identical Pods, kept at a given count.
---

A ReplicaSet keeps a stated number of Pods running with identical labels. It is
the mechanism underneath every [Deployment](/form?apiVersion=apps/v1&kind=Deployment):
the Deployment owns the rolling update, and the ReplicaSet owns the "keep N pods
alive" part.

You will rarely write one. It exists so that the Deployment's job (deciding *how*
to replace pods) and the ReplicaSet's job (keeping *N* of them) can change
independently.

## Use it for

- Rarely, deliberately. A ReplicaSet is the right object when you want pods kept
  alive with no rollout behaviour at all.

## Use something else for

- The same thing, with rolling updates and a declarative history →
  [Deployment](/form?apiVersion=apps/v1&kind=Deployment)
- A workload that needs stable identities → [StatefulSet](/form?apiVersion=apps/v1&kind=StatefulSet)

## Watch out for

The `spec.selector` of a ReplicaSet is **immutable**. It is part of the object's
identity, because it says which Pods belong to it — and changing it would mean
the controller suddenly adopting or abandoning Pods. If you get the selector
wrong, the fix is to delete the ReplicaSet and create it again, not to patch it.
