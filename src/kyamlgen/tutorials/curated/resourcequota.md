---
kind: ResourceQuota
summary: Caps how much of a namespace a set of objects may use.
---

A ResourceQuota limits the total resources — CPU, memory, object count — that
the objects in one namespace may consume. When a new object would exceed the
quota, the API server refuses to create it.

It is a guard rail, not a scheduler. The quota does not reserve capacity; it
simply starts saying no.

## Use it for

- Stopping one team from consuming the whole cluster.
- Putting a ceiling on the cost of a namespace.
- Forcing cleanup by making orphan objects cost something.

## Use something else for

- Controlling *where* workloads run → node selectors, affinity, taints.
- Controlling *when* they run → a
  [CronJob](/form?apiVersion=batch/v1&kind=CronJob)'s schedule.
- Limiting what a workload may *do* → RBAC, which is a different kind of limit
  entirely.

## Watch out for

**A quota with no matching scope is worse than no quota.** If you set
`requests.cpu` but your workloads do not set `requests.cpu`, then the quota
counts nothing and the limit is not enforced. Quotas count what is *declared*,
not what is used.

**A quota can block its own namespace from working.** A quota that requires
`limits.memory` on every container means a Pod without a memory limit is
rejected — including the Pod that would have cleaned things up.

And a namespace whose quota is exhausted is a namespace where nothing can be
created, including the Pod you need to fix the problem. That is why
`kubectl describe quota` is worth reading before a quota is tightened.
