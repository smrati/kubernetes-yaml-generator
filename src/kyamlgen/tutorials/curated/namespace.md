---
kind: Namespace
summary: A virtual cluster inside the cluster — a boundary for names, access and quotas.
---

A Namespace is a scope for names. Two objects with the same name can coexist in
different namespaces, and `metadata.namespace` is what tells them apart. It is
also the unit that access control and resource limits attach to.

It is not security isolation on its own. Namespaces segment *names* and
*policy*; whether one workload can reach another's network is a
[NetworkPolicy](/form?apiVersion=networking.k8s.io/v1&kind=NetworkPolicy)
question, and whether it can use too much CPU is a
[ResourceQuota](/form?apiVersion=v1&kind=ResourceQuota) question.

## Use it for

- Separating environments: `staging`, `production`, `dev`.
- Giving a team its own corner of the cluster with its own RBAC and quotas.
- Keeping a workload's resources together so they can be cleaned up as a unit.

## Use something else for

- Isolating workloads from each other on the same team →
  [NetworkPolicy](/form?apiVersion=networking.k8s.io/v1&kind=NetworkPolicy)
- A logical grouping inside one namespace → labels, which are a different tool
  for a different job.

## Watch out for

Deleting a namespace deletes everything in it, and Kubernetes has no undo. The
namespace controller runs the deletion in the background, and a namespace stuck
in `Terminating` usually means something in it has a finalizer that will not
clear.

The second thing is that `kubectl get pods -A` is the command you actually want.
Objects with no `metadata.namespace` land in `default`, and `default` is where
things end up when nobody set a namespace — which is how a namespace boundary
silently leaks.
