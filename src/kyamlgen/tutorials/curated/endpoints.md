---
kind: Endpoints
summary: The list of addresses behind a Service — normally created by Kubernetes, not by you.
---

An Endpoints object is the list of Pod addresses that a
[Service](/form?apiVersion=v1&kind=Service) forwards to. The Service controller
maintains it: it watches the Service's selector and rewrites the Endpoints
object whenever the set of matching Pods changes.

That means an Endpoints object you write by hand will be overwritten.

## Use it for

- Rarely, deliberately: pointing a Service at Pods that have no labels to select
  on. The Service's `spec.selector` must then be absent, or the controller will
  overwrite your Endpoints with an empty list.

## Use something else for

- The normal case → let the [Service](/form?apiVersion=v1&kind=Service) manage it.
- Per-pod conditions such as readiness → [EndpointSlice](/form?apiVersion=discovery.k8s.io/v1&kind=EndpointSlice),
  which is the modern replacement and carries the conditions that Endpoints
  cannot.

## Watch out for

If you create an Endpoints object by hand alongside a Service that *has* a
selector, the controller manages it and your list is replaced within seconds.
The symptom is a Service that mysteriously has no endpoints.

The modern API is EndpointSlice. Endpoints is still supported and still
generated for compatibility, but new tooling should use EndpointSlice — it
scales better, and it can express per-endpoint conditions and multiple addresses
per Pod.
