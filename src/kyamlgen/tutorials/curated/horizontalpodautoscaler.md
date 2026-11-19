---
kind: HorizontalPodAutoscaler
summary: Scales a workload's replica count up and down as load changes.
---

A HorizontalPodAutoscaler watches a metric — usually CPU or memory — and changes
the `replicas` field of the workload it targets. It does not create Pods
itself; it asks a Deployment to have more or fewer.

The target has to be a workload that implements the `scale` subresource, which
means a Deployment, a StatefulSet or a ReplicaSet.

## Use it for

- A service whose load varies and whose replicas are interchangeable.
- Saving money by running fewer replicas overnight.

## Use something else for

- A workload that cannot be scaled — a
  [StatefulSet](/form?apiVersion=apps/v1&kind=StatefulSet) with per-replica
  storage does not scale down cleanly, because the data has to move.
- Scheduling on node *counts* → the cluster autoscaler, which adds and removes
  nodes.
- Scaling on a custom metric → KEDA, or a custom HPA with an external metric
  source.

## Watch out for

**The HPA needs the target to exist.** `scaleTargetRef` names a kind and a name,
and if nothing matches, the HPA reports an error in its conditions and does
nothing. There is no warning at creation time.

The second is the metric's `averageUtilization`. It is a percentage *of the
request*, not of the node. A container that requests 100m and uses 80m is at 80%
utilisation, even on a node with 32 cores and nothing else running. That is why
a CPU-based HPA needs `resources.requests` to be set correctly — without
requests, there is no baseline to be a percentage of.

The third is that scaling up is fast and scaling down is slow. The default
stabilisation window is five minutes in each direction, which is deliberate: a
scale-down during a traffic spike is much worse than a slow scale-up.
