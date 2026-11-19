---
kind: Job
summary: Runs a task to completion, then stops.
---

A Job creates one or more Pods and waits for them to succeed. When they do, the
Job is done and its Pods stay around as history until you clean them up.

It is the batch equivalent of a Deployment: you describe work that should happen
exactly once (or a stated number of times), rather than a service that should
always be running.

## Use it for

- A migration, a backup, a report — work with a beginning and an end.
- Work that must succeed before something else starts.

## Use something else for

- Work on a recurring schedule → [CronJob](/form?apiVersion=batch/v1&kind=CronJob)
- A long-running service → [Deployment](/form?apiVersion=apps/v1&kind=Deployment)

## Watch out for

`restartPolicy` must be `Never` or `OnFailure` for a Job. `Always` is the
default for a Pod, and the Job controller rejects it — a Job that restarted
forever would never finish.

The other thing to know is that `completions` and `parallelism` are the two
different axes people confuse. `parallelism` is how many run at once.
`completions` is how many must succeed in total. The common "run this 100
times, 10 at a time" is `completions: 100` with `parallelism: 10`.

And a Job that keeps failing is not finished — it retries until `backoffLimit` is
reached, and only then does it report failure. If your CI waits on the Job and
the Job is failing slowly, that is why.
