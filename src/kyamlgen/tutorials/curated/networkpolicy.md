---
kind: NetworkPolicy
summary: Restricts which pods may talk to which.
---

A NetworkPolicy selects pods by label and then says what traffic they may
receive or send. Everything not explicitly allowed is denied.

The subtlety is in what happens when a policy selects *some* pods. For a given
direction, a pod is isolated if **any** policy selects it. So adding one
NetworkPolicy for one application can cut off traffic to every other pod in the
namespace, in that direction, for traffic that was previously allowed.

## Use it for

- Making one application's Pods unable to reach another's.
- Denying all egress except to specific destinations — the standard defence
  against a compromised pod exfiltrating data.

## Use something else for

- Separating teams → [Namespace](/form?apiVersion=v1&kind=Namespace)
- Controlling resource usage → [ResourceQuota](/form?apiVersion=v1&kind=ResourceQuota)

## Watch out for

**Declaring `policyTypes` matters.** A policy with only `ingress` rules still
allows *all* egress. If you want egress restricted, you have to say
`Egress` in `policyTypes` and write the egress rules. This surprises people
regularly: a policy that looks like a lockdown is not one.

The second is that NetworkPolicy needs a network plugin that enforces them. On a
cluster with a plugin that does not — or on some managed clusters where the
default plugin is a pass-through — the policies are accepted and ignored. The
object is not evidence that the restriction is in force.

The third is DNS. Once you restrict egress, `dns` on UDP port 53 is usually
still needed, and the kube-dns Service has to be allowed explicitly.
