---
kind: EndpointSlice
summary: The modern list of addresses behind a Service — with per-endpoint conditions.
---

An EndpointSlice is the current version of what an
[Endpoints](/form?apiVersion=v1&kind=Endpoints) object used to be: a list of
the addresses a [Service](/form?apiVersion=v1&kind=Service) routes to. The
Service controller maintains it, exactly as it maintained Endpoints.

It exists because Endpoints does not scale and cannot say much. An EndpointSlice
holds up to 100 addresses, and each address carries **conditions** — ready,
serving, terminating — so the proxy knows which endpoints to use and which are
on their way out.

## Use it for

- Rarely, deliberately. The controller writes these.
- Giving a Service manual endpoints, the same way Endpoints objects were used
  before.

## Use something else for

- The normal case → let the [Service](/form?apiVersion=v1&kind=Service) manage
  it.
- Legacy tooling → [Endpoints](/form?apiVersion=v1&kind=Endpoints), which the
  controller still maintains for compatibility.

## Watch out for

If you create an EndpointSlice by hand next to a Service that has a selector,
the controller manages it and your list is replaced.

The thing worth knowing is the condition model. `ready: false` means the endpoint
is not ready to receive traffic. `serving: true` with `terminating: true` means
the Pod is on its way out but should keep serving until it is drained — that
combination is what makes rolling updates seamless, and it is why a Service
behind a rolling Deployment stays available.

`addressType` decides what goes in `addresses[].value`: `IPv4`, `IPv6`, or
`FQDN`. It is immutable.
