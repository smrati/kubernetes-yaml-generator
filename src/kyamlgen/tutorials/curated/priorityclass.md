---
kind: PriorityClass
summary: Names a scheduling priority, so a Pod can ask to be scheduled first.
---

A PriorityClass names a priority value and says whether the cluster should
create pods for it when there is not enough capacity.

The value itself is just an integer. Higher means more important. The scheduler
sorts pending Pods by priority and admits them in that order.

## Use it for

- Making a control-plane or data-plane component win a scheduling contest.
- Saying that one workload matters more than another when the cluster is full.

## Use something else for

- Deciding *where* a Pod runs → node selectors, affinity, taints.
- Preempting a running Pod to make room → `preemptionPolicy: PreemptLowerPriority`,
  which this class sets.

## Watch something else for

**Higher priority does not mean faster scheduling if there is room.** Priority
only matters when Pods are waiting. In a cluster with spare capacity, every Pod
starts immediately whatever its priority.

**`preemptionPolicy: PreemptLowerPriority` evicts running Pods to make room,
and those Pods are usually not restarted fast enough to be harmless.** A
preempted Pod goes back to Pending. If it was a
[Deployment](/form?apiVersion=apps/v1&kind=Deployment), a new Pod is created
elsewhere — but that is not the same as the Pod that was running.

The value of `priorityClassName` on a Pod is read at creation and cannot be
changed afterwards. A Pod's priority is also what the scheduler uses when it
preempts, and it is bounded by the PriorityClass's `value`.
