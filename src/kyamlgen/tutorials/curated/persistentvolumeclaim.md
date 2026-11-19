---
kind: PersistentVolumeClaim
summary: A request for storage — you ask, the cluster provides.
---

A PersistentVolumeClaim is a request for storage with a name. You say how much
you want and how you intend to use it; the cluster finds a matching
[PersistentVolume](/form?apiVersion=v1&kind=PersistentVolume) or provisions a
new one, and binds the two.

The two-layer design exists because the user and the cluster care about different
things. You know your application's needs — size, access mode. The
[StorageClass](/form?apiVersion=storage.k8s.io/v1&kind=StorageClass) knows the
infrastructure — what disks exist, what they cost, how to make more.

## Use it for

- Storage that survives the Pod using it.
- Decoupling an application from the storage technology underneath it.

## Use something else for

- Per-replica storage for a [StatefulSet](/form?apiVersion=apps/v1&kind=StatefulSet)
  — its `volumeClaimTemplates` create the claims for you, one per replica.
- Data that is genuinely temporary →
  [emptyDir](https://kubernetes.io/docs/concepts/storage/volumes/#emptydir) in the
  Pod spec.

## Watch out for

**`spec.resources.requests.storage` is the only size that matters.** The field
is called `requests`, but for a claim it is not a request — it is the exact
amount you get. Asking for 1Gi gives you 1Gi.

The second is `accessModes`. `ReadWriteOnce` means one *node* can mount it
read-write, which does **not** mean one Pod. A Deployment with two replicas on
different nodes cannot use a `ReadWriteOnce` volume, and the second Pod stays
`Pending` with a mount error.

The third is that a claim can be stuck `Pending` for a long time. The usual
cause is a storage class whose provisioner cannot actually deliver in your
region. `kubectl describe pvc` names the provisioner and the error.
