---
kind: Service
summary: A stable name and address for a set of Pods, and the thing that routes traffic to them.
---

A Service is a named abstraction in front of a set of Pods. It has its own
address, and it forwards traffic to whichever Pods currently match its selector.
The Pods behind it come and go; the Service does not change.

This is the piece people miss when they first meet Kubernetes. A Pod's IP
address is not a stable thing to build on — it changes when the Pod is
replaced. The Service is the stable thing.

## Use it for

- Giving a workload a name that other things can connect to.
- Exposing a workload inside or outside the cluster.
- Separating the port clients use from the port the container listens on.

## Use something else for

- Routing HTTP in from outside the cluster → [Ingress](/form?apiVersion=networking.k8s.io/v1&kind=Ingress)
- A stable identity or per-replica storage → [StatefulSet](/form?apiVersion=apps/v1&kind=StatefulSet)

## Watch out for

**A Service does not select Pods by name.** It selects them by *label*, and that
is the single most common source of confusion:

```yaml
spec:
  selector:
    app: my-api     # ← matches labels, not names
```

If the Deployment's pod template labels do not include this, the Service is
created, gets an IP, and has no endpoints. Nothing errors. Traffic just times
out.

The second thing is the two ports.
[spec.ports[].port](field:spec.ports[].port) is what a client connects to;
[spec.ports[].targetPort](field:spec.ports[].targetPort) is the port on the
container. They are frequently different numbers. Naming the container port and
using the *name* for `targetPort` keeps the two in step when the container port
changes — which is the smallest possible version of the coupling problem this
tool exists to catch.
