---
kind: Role
summary: A set of permissions within one namespace.
---

A Role says what a subject may do, and only within one namespace. It is a list
of rules, and each rule is a set of API groups, resources and verbs.

Roles grant nothing by themselves. A Role has to be bound to a subject with a
[RoleBinding](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=RoleBinding).

## Use it for

- Letting one workload read the ConfigMaps in its own namespace.
- Giving a team access to their own corner of the cluster.

## Use something else for

- Permissions across all namespaces →
  [ClusterRole](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=ClusterRole),
  bound with a
  [ClusterRoleBinding](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=ClusterRoleBinding).
- Built-in permissions → the `view`, `edit`, `admin` and `cluster-admin`
  ClusterRoles that ship with Kubernetes.

## Watch out for

**A rule with an empty resource list grants nothing, and a rule with an empty
verb list grants nothing.** This is a common mistake when writing YAML by hand
and it fails silently — the binding exists, the Role exists, and the subject
still gets "forbidden".

The second is `apiGroups: ["*"]` with `resources: ["*"]` and `verbs: ["*"]`.
That is full access, and it is the difference between a namespace-scoped Role
and a cluster-admin. In a namespace it is still a very large permission.

The third is that a Role cannot grant access to a cluster-scoped resource —
nodes, persistent volumes, namespaces themselves. Those need a
[ClusterRole](/form?apiVersion=rbac.authorization.k8s.io/v1&kind=ClusterRole),
even if the subject is a namespace-scoped ServiceAccount.
