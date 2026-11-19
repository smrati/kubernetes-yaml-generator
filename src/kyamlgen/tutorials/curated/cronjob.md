---
kind: CronJob
summary: Creates Jobs on a schedule.
---

A CronJob creates [Jobs](/form?apiVersion=batch/v1&kind=Job) according to a
schedule. The Job does the work; the CronJob only decides when.

The schedule is five fields — minute, hour, day-of-month, month, day-of-week — in
UTC. `0 3 * * *` is 03:00 every day.

## Use it for

- Nightly reports, hourly syncs, periodic cleanup.

## Use something else for

- Work that should happen once and be waited on → [Job](/form?apiVersion=batch/v1&kind=Job)
- A service → [Deployment](/form?apiVersion=apps/v1&kind=Deployment)

## Watch out for

**The time zone is UTC.** Not your laptop's time zone, not the cluster's. A
schedule of `0 3 * * *` runs at 03:00 UTC, which is 08:30 in Mumbai. If that
matters, set `timeZone` explicitly — it needs a cluster with the `TimeZone`
feature, which is standard from Kubernetes 1.27.

The second thing is `concurrencyPolicy`. The default is `Allow`, which means a
new Job starts even if the last one has not finished. If your job is not safe to
run twice at once, that is the field to change.

The third is the history limit. `successfulJobsHistoryLimit` and
`failedJobsHistoryLimit` control how many finished Jobs are kept for
inspection. The defaults are 3 and 1.
