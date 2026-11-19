---
kind: PodDisruptionBudget
summary: Caps how many Pods a voluntary disruption — a node drain, a cluster upgrade — may take down at once.
---

A PodDisruptionBudget limits the number of Pods that may be unavailable
voluntarily. When the cluster drains a node or an administrator upgrades the
cluster, the eviction API refuses to evict more Pods than the budget allows.

It is not a health check and it does not protect against involuntary
disruption — a node dying takes its Pods down regardless. It only governs
evictions.

## Use it for

- Keeping a quorum-based application available during node maintenance.
- Any workload where a simultaneous restart of every replica would be noticed.

## Use something else for

- Keeping a Deployment's replicas up during a rollout → the Deployment's own
  [maxUnavailable](/form?apiVersion=apps/v1&kind=Deployment), which governs
  voluntary disruption caused by the rollout.
- Application-level availability → a
  [Deployment](/form?apiVersion=apps/v1&kind=Deployment) with enough replicas.

## Watch out for

**The budget selects Pods by label, and the selector has to match the pod
template's labels.** A PDB whose selector matches nothing matches *no* Pods, so
the budget allows everything — it looks like it is protecting something and it is
not.

The second is that `minAvailable` and `maxUnavailable` are alternatives, not a
pair. Set one or the other. With `minAvailable: 1`, a single-replica deployment
can never be evicted at all — which is correct, but it means node drains will
hang rather than fail.

The third is that a PDB can block cluster upgrades indefinitely. That is the
intent, but it is why PDBs get removed in a hurry during an incident, and why
`maxUnavailable: 1` on a five-replica deployment is often the more practical
setting.
