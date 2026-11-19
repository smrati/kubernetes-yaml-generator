---
kind: Ingress
summary: Routes HTTP and HTTPS traffic from outside the cluster to Services inside it.
---

An Ingress is a rule set: given this host and this path, send the traffic to
that Service. It is the cluster's front door for HTTP.

It does not proxy anything itself. It describes routing, and the controller that
implements it — nginx, Traefik, a cloud load balancer — does the actual work.
That is why `Ingress` alone tells you very little about what will actually
happen; `IngressClass` is what picks the implementation.

## Use it for

- Exposing HTTP services through a single host and path structure.
- Terminating TLS for several services at once.

## Use something else for

- Non-HTTP traffic → a [Service](/form?apiVersion=v1&kind=Service) of type
  `LoadBalancer`, or a cloud load balancer resource.
- Routing inside the cluster → a [Service](/form?apiVersion=v1&kind=Service).
  Services do not need an Ingress to talk to each other.

## Watch out for

The backend of a path is a Service **and a port**, and both have to be right.
The Service has to exist, and it has to expose the port you point at. An Ingress
that names a Service that is not there is accepted by the API server and serves
503s for every request.

The second thing is `pathType`. It is required, and the three values are not
interchangeable:

- `Exact` — the path must match exactly.
- `Prefix` — matched by path segments, not by string prefix. `/api` matches
  `/api/users` but *not* `/apifoo`, because the split is on `/`.
- `ImplementationSpecific` — the controller decides, and different controllers
  decide differently.

`ImplementationSpecific` is the default in the old API and a source of
inconsistency between controllers. Prefer `Exact` or `Prefix`.
