---
kind: LimitRange
summary: Default and maximum values for the resource requests and limits of containers.
---

A LimitRange does two things. It supplies **defaults** — a container with no
memory limit gets the one you specify — and it sets **maximums**, so a container
that asks for more than the range allows is rejected at creation time.

It is the quieter sibling of [ResourceQuota](/form?apiVersion=v1&kind=ResourceQuota).
The quota caps the namespace in total; the limit range caps each container and
fills in what was left out.

## Use it for

- Making resource requests mandatory by default, so the
  [HorizontalPodAutoscaler](/form?apiVersion=autoscaling/v2&kind=HorizontalPodAutoscaler)
  has a baseline to work from.
- Stopping one container from claiming an unreasonable share of a node.

## Use something else for

- A namespace-wide total → [ResourceQuota](/form?apiVersion=v1&kind=ResourceQuota)
- Constraining ephemeral storage or the number of objects → those are
  ResourceQuota's job, not a LimitRange's.

## Watch out for

**Default limits and default requests are different numbers, and that is
deliberate.** The usual pattern is a request of 100m/128Mi and a limit of
500m/512Mi — so a container is *scheduled* on what it needs and *capped* at what
it may burst to. If you set defaults the other way round, every container is
scheduled as if it will use its maximum.

The second is that a LimitRange applies to containers that **do not specify**
the field. A container that sets its own limit is unaffected by the default —
only the maximums still apply.

The third is that a LimitRange with `max` but no `defaultRequest` does not make
requests mandatory; it only rejects the ones that are too large. To require
requests, the `defaultRequest` has to be present.
