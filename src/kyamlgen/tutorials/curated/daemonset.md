---
kind: DaemonSet
summary: One Pod on every node — for agents that have to run everywhere.
---

A DaemonSet runs exactly one Pod on each node in the cluster. There is no
`replicas` field, because the count *is* the number of nodes.

It is the right shape for anything that is per-node rather than per-service: a
log shipper, a metrics agent, a network plugin, a node exporter.

## Use it for

- Collecting logs, metrics or traces from every node.
- Something that must run on every node regardless of how many nodes there are.

## Use something else for

- A service that should scale with load → [Deployment](/form?apiVersion=apps/v1&kind=Deployment)
- A task that runs to completion → [Job](/form?apiVersion=batch/v1&kind=Job)

## Watch out for

Because a DaemonSet adds a Pod to every node, adding one to a cluster with
hundreds of nodes adds hundreds of Pods. On a large cluster the rollout is
bounded by the rate at which the controller can create Pods, which can be slow —
`maxUnavailable` is what controls how many nodes are disrupted at once during
that rollout.

A DaemonSet also runs on nodes that do not match your workload's needs. If your
agent should not run on control-plane nodes, say so with a
`nodeSelector` or tolerations — the DaemonSet has no opinion, and will happily
schedule onto a node where it cannot work.
