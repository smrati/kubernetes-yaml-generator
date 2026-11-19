---
kind: PersistentVolume
summary: A piece of storage in the cluster, independent of any Pod.
---

A PersistentVolume is a piece of storage that exists on its own. It outlives the
Pods that use it, and it is what a
[PersistentVolumeClaim](/form?apiVersion=v1&kind=PersistentVolumeClaim) binds to.

In a managed cluster you will rarely write one: the storage class provisions
them. But the distinction matters, because it explains the two-layer design.

## Use it for

- Storage that must survive a Pod, a node, or a Deployment rollout.
- Storage that is explicitly provisioned rather than requested on demand.

## Use something else for

- Almost always → [PersistentVolumeClaim](/form?apiVersion=v1&kind=PersistentVolumeClaim).
  You ask for storage; the cluster finds or makes a volume for you.
- Storage that belongs to one workload →
  [StatefulSet](/form?apiVersion=apps/v1&kind=StatefulSet)'s `volumeClaimTemplates`,
  which creates the claim per replica.

## Watch out for

**A PV's `claimRef` records who it is bound to, and it is not mutable.** A PV
that is bound to a claim stays bound — even if the claim is deleted, the PV goes
to `Released` and has to be reclaimed deliberately. That is a safety feature, not
a bug.

The second is `persistentVolumeReclaimPolicy`. `Retain` keeps the data when the
claim is deleted, which is what you want for anything you would be upset to
lose. `Delete` destroys it. The default is `Delete` for dynamically provisioned
volumes, and it is worth noticing that in most cloud storage classes the
underlying disk is deleted with it.

The third is capacity. A `Local` volume is a directory on one node. The Pod that
uses it is pinned to that node, and it cannot be rescheduled elsewhere.
