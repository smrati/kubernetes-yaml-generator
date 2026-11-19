---
kind: Pod
summary: The smallest thing Kubernetes schedules — one or more containers that share a network and a lifetime.
---

A Pod is a group of containers that run together on the same node and share the
same IP address and the same volumes. It is the unit that Kubernetes schedules:
the scheduler picks a node for a Pod, never for a container.

Pods are **not** durable. Nothing creates them, nothing replaces them, and
nothing restarts them with a new image. A Pod is a short-lived thing that a
controller decides should exist.

That is why you almost never write one directly. The thing you actually want —
a service that stays up, scales, and rolls out — is a
[Deployment](/form?apiVersion=apps/v1&kind=Deployment), and the Deployment
creates Pods for you.

## Use it for

- A debugging pod: `kubectl run` gives you one in a terminal without writing YAML.
- A one-shot task that has to run in a particular way →
  [Job](/form?apiVersion=batch/v1&kind=Job).

## Use something else for

- Anything long-lived → [Deployment](/form?apiVersion=apps/v1&kind=Deployment)
- A task that runs to completion → [Job](/form?apiVersion=batch/v1&kind=Job)
- A task on a schedule → [CronJob](/form?apiVersion=batch/v1&kind=CronJob)

## Watch out for

Two containers in one Pod are a deliberate choice, not a convenience. They share a
network namespace — they can reach each other on `localhost` — and they share
volumes. That is how you run a sidecar proxy next to your application without
paying for a second Pod's worth of scheduling and networking.

If you find yourself adding a second container because "the app needs a
database", the answer is usually two Deployments and a Service, not two
containers.
