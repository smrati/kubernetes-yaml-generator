---
kind: StorageClass
summary: Describes a class of storage — what it is, how it is provisioned, and what happens when it is deleted.
---

A StorageClass is how a cluster describes a *kind* of storage: "fast SSD, on
this cloud, provisioned on demand, deleted with the volume". A
[PersistentVolumeClaim](/form?apiVersion=v1&kind=PersistentVolumeClaim) that
names a storage class asks for that kind; one that does not gets the cluster's
default class.

## Use it for

- Telling the cluster what storage to hand out and how to make more of it.
- Differentiating tiers — fast local SSD for a database, cheap object storage
  for backups.

## Use something else for

- Requesting storage → [PersistentVolumeClaim](/form?apiVersion=v1&kind=PersistentVolumeClaim)
- A volume you provision yourself → [PersistentVolume](/form?apiVersion=v1&kind=PersistentVolume)

## Watch out for

`reclaimPolicy` is the field that decides whether your data survives. `Delete`
destroys the underlying storage when the claim is deleted; `Retain` keeps it and
leaves the volume in `Released` for an administrator to clean up. For anything
you would be upset to lose, `Retain` is the safer default, and it is worth
knowing that many cloud storage classes default to `Delete`.

`volumeBindingMode` decides *when* the volume is provisioned. `WaitForFirstConsumer`
— the default — delays provisioning until a Pod actually needs it, which lets the
scheduler pick a node in the right zone. `Immediate` provisions it up front, in
whatever zone happens to be available, and can put your Pod and its data in
different places.

The third is `allowVolumeExpansion`. Without it, a claim cannot be resized, and
growing a database's disk means migrating it.
