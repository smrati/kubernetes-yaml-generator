"""Cross-object semantics — the layer that a schema cannot express.

A Kubernetes schema checks one object in isolation.  It therefore cannot notice the
failure that actually bites in practice: a Deployment and a Service that each look
perfectly valid but do not agree with each other.  The Deployment deploys, the Service
is created, and nothing routes because the selector does not match the pod labels.

The rules below encode the agreements Kubernetes expects between objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .validate import Issue

#: Kinds whose pod template lives at ``spec.template``.
TEMPLATE_WORKLOADS = {
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "ReplicaSet",
    "Job",
}

#: Kinds that own a pod template and are expected to carry a selector.
SELECTOR_WORKLOADS = TEMPLATE_WORKLOADS

#: Long-running workloads where a health probe is expected.
PROBE_EXPECTED = {"Deployment", "StatefulSet", "DaemonSet"}

#: Kinds that own a pod template, and so can have containers in them.
POD_OWNING = TEMPLATE_WORKLOADS | {"CronJob", "Pod"}


@dataclass(frozen=True)
class Relationship:
    """A connection between two kinds, and the check that catches a mismatch.

    The rule table says which kinds a *check* applies to.  This says which kinds
    actually reference each other.  They are different questions: "a Deployment has
    no image tag" concerns a Deployment on its own, while "a Service finds your
    pods" relates a Service and a Deployment.

    The relationship is directional — one side initiates, the other is referenced —
    because the counterpart set depends on which side you are looking at.  For a
    Deployment the counterpart of the ConfigMap relationship is "ConfigMap"; for a
    ConfigMap it is "the kinds that can reference me".
    """

    initiator: tuple[str, ...]
    target: tuple[str, ...]
    sentence: str
    rule: str | None = None

    def counterpart(self, kind: str) -> tuple[str, ...] | None:
        """The other side of the relationship, from one kind's point of view."""
        if kind in self.initiator:
            return self.target
        if kind in self.target:
            return self.initiator
        return None


#: The connections a learner needs to know about, in teaching order.
#:
#: The sentences are written so the same line reads correctly on both sides.
RELATIONSHIPS: tuple[Relationship, ...] = (
    Relationship(
        ("Service",),
        POD_OWNING,
        "A Service finds the pods it routes to by their labels, so the labels on "
        "your pods and the Service's selector have to agree.",
        "service-selector-unmatched",
    ),
    Relationship(
        ("Service",),
        POD_OWNING,
        "A Service reaches your containers through targetPort, so it has to name a "
        "port they actually open.",
        "target-port-unmatched",
    ),
    Relationship(
        ("Ingress",),
        ("Service",),
        "An Ingress routes HTTP traffic to a Service by name, and to a port that Service exposes.",
        "ingress-backend-missing",
    ),
    Relationship(
        ("HorizontalPodAutoscaler",),
        ("Deployment", "StatefulSet", "ReplicaSet"),
        "A HorizontalPodAutoscaler changes how many replicas a workload has, and "
        "the workload has to implement the scale subresource.",
        "scaler-target-missing",
    ),
    Relationship(
        POD_OWNING,
        ("ConfigMap",),
        "A pod template can read a ConfigMap for its configuration. If the "
        "ConfigMap is not there, the pod cannot start.",
        "dangling-reference",
    ),
    Relationship(
        POD_OWNING,
        ("Secret",),
        "A pod template can read a Secret for its credentials. If the Secret is not "
        "there, the pod cannot start.",
        "dangling-reference",
    ),
    Relationship(
        POD_OWNING,
        ("PersistentVolumeClaim",),
        "A pod template can mount a PersistentVolumeClaim for its storage. If the "
        "claim is not there, the pod stays Pending.",
        "dangling-reference",
    ),
    Relationship(
        ("PodDisruptionBudget",),
        POD_OWNING,
        "A PodDisruptionBudget selects the pods it protects, so it has to select "
        "them the same way a Service does.",
        "pdb-selector-unmatched",
    ),
    Relationship(
        ("RoleBinding",),
        ("Role", "ClusterRole", "ServiceAccount"),
        "A RoleBinding grants a role to a subject, so the role and the service "
        "account both have to exist.",
        "role-binding-ref-missing",
    ),
    Relationship(
        ("ClusterRoleBinding",),
        ("ClusterRole", "ServiceAccount"),
        "A ClusterRoleBinding grants a cluster role to a subject, so the role and "
        "the service account both have to exist.",
        "cluster-role-binding-ref-missing",
    ),
)


def relationships_for(kind: str) -> list[dict[str, Any]]:
    """The relationships a kind takes part in, with the other side named."""
    out: list[dict[str, Any]] = []
    for relationship in RELATIONSHIPS:
        other = relationship.counterpart(kind)
        if other is None:
            continue
        out.append(
            {
                "kinds": list(other),
                "sentence": relationship.sentence,
                "rule": relationship.rule,
            }
        )
    return out


@dataclass(frozen=True)
class Rule:
    """One cross-object rule, and the kinds it concerns.

    The tutorial's "how it connects" section is derived from this table, so the
    tutorial and the checker cannot drift apart: there is one description of each
    rule and both the code and the prose read it.
    """

    code: str
    kinds: frozenset[str]
    summary: str

    def involves(self, kind: str) -> bool:
        return "*" in self.kinds or kind in self.kinds

    def others(self, kind: str) -> list[str]:
        """The other kinds this rule connects, for a given kind."""
        if "*" in self.kinds:
            return []
        return sorted(self.kinds - {kind})


#: Every rule the semantic engine can raise.
#:
#: ``kinds`` names the kinds a rule connects.  A rule that relates two kinds lists
#: both, which is what lets the tutorial say "a Service connects to a Deployment"
#: without anyone maintaining a second list.
RULES: tuple[Rule, ...] = (
    Rule(
        "selector-template-mismatch",
        frozenset({"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job"}),
        "A workload's selector must match the labels on its own pod template. "
        "If it does not, the workload manages no pods at all — and it still "
        "reports them as Running.",
    ),
    Rule(
        "service-empty-selector",
        frozenset({"Service"}),
        "A Service with no selector routes to nothing. That is sometimes what "
        "you want (an ExternalName Service, or manual endpoints), and often not.",
    ),
    Rule(
        "service-selector-unmatched",
        frozenset({"Service"} | POD_OWNING),
        "A Service selects pods by their labels, not by name. Its selector has "
        "to match the labels on the pods it is meant to route to, or the Service "
        "gets no endpoints and every request times out.",
    ),
    Rule(
        "target-port-unmatched",
        frozenset({"Service"} | POD_OWNING),
        "A Service's targetPort has to reach a port the container actually opens "
        "— either the number, or the name of a named container port.",
    ),
    Rule(
        "dangling-reference",
        frozenset(POD_OWNING | {"ConfigMap", "Secret", "PersistentVolumeClaim"}),
        "A pod template that references a ConfigMap, a Secret or a PVC needs "
        "that object to exist, or the pod cannot start.",
    ),
    Rule(
        "ingress-backend-missing",
        frozenset({"Ingress", "Service"}),
        "An Ingress routes to a Service by name. If the Service is not there, "
        "the Ingress is accepted and serves 503s.",
    ),
    Rule(
        "ingress-backend-port-missing",
        frozenset({"Ingress", "Service"}),
        "An Ingress backend points at a Service *and* a port. The Service has to expose that port.",
    ),
    Rule(
        "scaler-target-missing",
        frozenset({"HorizontalPodAutoscaler", "Deployment", "StatefulSet", "ReplicaSet"}),
        "A HorizontalPodAutoscaler scales a named workload. The workload has to "
        "exist, and it has to implement the scale subresource.",
    ),
    Rule(
        "role-binding-ref-missing",
        frozenset({"RoleBinding", "Role", "ClusterRole", "ServiceAccount"}),
        "A RoleBinding grants a role to a subject. If the role or the service "
        "account is not there, the binding is accepted and grants nothing.",
    ),
    Rule(
        "cluster-role-binding-ref-missing",
        frozenset({"ClusterRoleBinding", "ClusterRole", "ServiceAccount"}),
        "A ClusterRoleBinding grants a cluster-scoped role to a subject. If the "
        "role or the service account is not there, the binding grants nothing.",
    ),
    Rule(
        "pdb-selector-unmatched",
        frozenset({"PodDisruptionBudget"} | POD_OWNING),
        "A PodDisruptionBudget selects the pods it protects. If the selector "
        "matches nothing, it protects nothing and still looks correct.",
    ),
    Rule(
        "namespace-mismatch",
        frozenset({"*"}),
        "Objects in one file are usually applied to one namespace. A file where "
        "some objects name a namespace and others do not is ambiguous.",
    ),
    Rule(
        "image-no-tag",
        frozenset(POD_OWNING),
        "An image with no tag resolves to :latest, which moves under you without "
        "the manifest changing. Pin a tag or a digest.",
    ),
    Rule(
        "no-probe",
        frozenset(PROBE_EXPECTED),
        "A long-running container with no probe gives Kubernetes no way to tell "
        "whether it is working. A failing container and a working one look the "
        "same.",
    ),
    Rule(
        "limit-without-request",
        frozenset(POD_OWNING),
        "A limit without a request makes the scheduler place the pod as if it "
        "were using the limit, which is usually not what you meant.",
    ),
)

#: Rule codes, for lookup.
RULE_BY_CODE = {rule.code: rule for rule in RULES}


def rules_for(kind: str) -> list[Rule]:
    """The rules that concern a kind."""
    return [rule for rule in RULES if rule.involves(kind)]


def _get(obj: dict[str, Any], *keys: str, default: Any = None) -> Any:
    node: Any = obj
    for key in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(key)
    return node if node is not None else default


def pod_template(obj: dict[str, Any]) -> dict[str, Any] | None:
    """Return the PodTemplateSpec of a workload object, if it has one."""
    kind = obj.get("kind")
    if kind == "Pod":
        return {"metadata": obj.get("metadata") or {}, "spec": obj.get("spec") or {}}
    if kind == "CronJob":
        template = _get(obj, "spec", "jobTemplate", "spec", "template")
        return template if isinstance(template, dict) else None
    if kind in TEMPLATE_WORKLOADS:
        template = _get(obj, "spec", "template")
        return template if isinstance(template, dict) else None
    return None


def template_labels(obj: dict[str, Any]) -> dict[str, str]:
    """Labels on a workload's pod template."""
    template = pod_template(obj)
    if not template:
        return {}
    labels = _get(template, "metadata", "labels", default={})
    return labels if isinstance(labels, dict) else {}


def selector_labels(obj: dict[str, Any]) -> dict[str, str]:
    """The label selector a workload applies to its own pods."""
    if obj.get("kind") not in SELECTOR_WORKLOADS:
        return {}
    match = _get(obj, "spec", "selector", "matchLabels", default={})
    return match if isinstance(match, dict) else {}


def containers(obj: dict[str, Any]) -> list[dict[str, Any]]:
    """Containers in a workload's pod template."""
    template = pod_template(obj)
    if not template:
        return []
    found = _get(template, "spec", "containers", default=[])
    return found if isinstance(found, list) else []


def _name(obj: dict[str, Any]) -> str:
    return _get(obj, "metadata", "name", default="<unnamed>")


def _namespace(obj: dict[str, Any]) -> str:
    return _get(obj, "metadata", "namespace", default="default")


def _has_tag(image: str) -> bool:
    """True when an image reference pins a tag or a digest."""
    if "@sha256:" in image:
        return True
    return ":" in image.rsplit("/", 1)[-1]


def _matching_workload(
    service_selector: dict[str, str], workloads: list[dict[str, Any]]
) -> dict[str, Any] | None:
    for workload in workloads:
        labels = template_labels(workload)
        if all(labels.get(key) == value for key, value in service_selector.items()):
            return workload
    return None


def analyse(objects: list[dict[str, Any]]) -> list[Issue]:
    """Run every cross-object rule over a bundle of manifests."""
    issues: list[Issue] = []
    workloads = [obj for obj in objects if pod_template(obj) is not None]
    services = [obj for obj in objects if obj.get("kind") == "Service"]
    config_maps = {_name(obj) for obj in objects if obj.get("kind") == "ConfigMap"}
    secrets = {_name(obj) for obj in objects if obj.get("kind") == "Secret"}
    claims = {_name(obj) for obj in objects if obj.get("kind") == "PersistentVolumeClaim"}

    issues.extend(_check_selector_matches_template(workloads))
    issues.extend(_check_service_selectors(services, workloads))
    issues.extend(_check_service_ports(services, workloads))
    issues.extend(_check_references(objects, config_maps, secrets, claims))
    issues.extend(_check_bindings(objects))
    issues.extend(_check_disruption_budgets(objects, workloads))
    issues.extend(_check_ingress_backends(objects, services))
    issues.extend(_check_scalers(objects, workloads))
    issues.extend(_check_namespaces(objects))
    issues.extend(_check_container_hygiene(workloads))
    return issues


def _check_selector_matches_template(workloads: list[dict[str, Any]]) -> list[Issue]:
    """A workload's selector must match the labels on its own pod template."""
    issues: list[Issue] = []
    for index, workload in enumerate(workloads):
        selector = selector_labels(workload)
        if not selector:
            continue
        labels = template_labels(workload)
        for key, value in selector.items():
            if labels.get(key) != value:
                issues.append(
                    Issue(
                        level="error",
                        code="selector-template-mismatch",
                        message=(
                            f"{workload['kind']} selector requires "
                            f"{key}={value} but its pod template has "
                            f"{key}={labels.get(key, '<missing>')}. The workload will "
                            f"not manage its own pods."
                        ),
                        path=["spec", "selector", "matchLabels"],
                        object_index=index,
                    )
                )
    return issues


def _check_service_selectors(
    services: list[dict[str, Any]], workloads: list[dict[str, Any]]
) -> list[Issue]:
    """A Service selector must match the pods it is meant to route to.

    A Service whose selector matches nothing in the bundle is only a problem when
    the bundle *contains* workloads — if it contains none, the pods it selects may
    already exist in the cluster, and the bundle is not the cluster.
    """
    issues: list[Issue] = []
    for index, service in enumerate(services):
        if service.get("spec", {}).get("type") == "ExternalName":
            continue
        selector = _get(service, "spec", "selector", default={})
        if not selector:
            issues.append(
                Issue(
                    level="warning",
                    code="service-empty-selector",
                    message=(
                        f"Service {_name(service)} has no selector, so it will not "
                        f"route to any pods."
                    ),
                    path=["spec", "selector"],
                    object_index=index,
                )
            )
            continue
        if not workloads:
            continue
        if _matching_workload(selector, workloads) is None:
            issues.append(
                Issue(
                    level="error",
                    code="service-selector-unmatched",
                    message=(
                        f"Service {_name(service)} selects "
                        f"{_format_selector(selector)} but no workload in this bundle "
                        f"carries those labels. The Service will have no endpoints."
                    ),
                    path=["spec", "selector"],
                    object_index=index,
                )
            )
    return issues


def _check_service_ports(
    services: list[dict[str, Any]], workloads: list[dict[str, Any]]
) -> list[Issue]:
    """A Service targetPort must reach a port that a container actually opens."""
    issues: list[Issue] = []
    for index, service in enumerate(services):
        ports = _get(service, "spec", "ports", default=[])
        if not isinstance(ports, list):
            continue
        selector = _get(service, "spec", "selector", default={}) or {}
        workload = _matching_workload(selector, workloads) if selector else None
        if workload is None:
            continue
        container_ports: dict[int, str] = {}
        port_names: dict[str, int] = {}
        for container in containers(workload):
            for port in container.get("ports") or []:
                number = port.get("containerPort")
                if isinstance(number, int):
                    container_ports[number] = container.get("name", "")
                if port.get("name"):
                    port_names[port["name"]] = number
        for port_index, port in enumerate(ports):
            target = port.get("targetPort")
            if target is None:
                continue
            if isinstance(target, int):
                if target not in container_ports:
                    issues.append(
                        Issue(
                            level="error",
                            code="target-port-unmatched",
                            message=(
                                f"Service {_name(service)} targets port {target} but "
                                f"{workload['kind']} {_name(workload)} does not expose "
                                f"that container port."
                            ),
                            path=["spec", "ports", str(port_index), "targetPort"],
                            object_index=index,
                        )
                    )
            elif isinstance(target, str) and target not in port_names:
                issues.append(
                    Issue(
                        level="error",
                        code="target-port-unmatched",
                        message=(
                            f"Service {_name(service)} targets the named port "
                            f"'{target}' but {workload['kind']} {_name(workload)} does "
                            f"not declare a container port with that name."
                        ),
                        path=["spec", "ports", str(port_index), "targetPort"],
                        object_index=index,
                    )
                )
    return issues


def _check_references(
    objects: list[dict[str, Any]],
    config_maps: set[str],
    secrets: set[str],
    claims: set[str],
) -> list[Issue]:
    """ConfigMaps, Secrets and PVCs referenced by a workload should be present."""
    issues: list[Issue] = []
    for index, obj in enumerate(objects):
        if pod_template(obj) is None and obj.get("kind") != "Pod":
            continue
        for container in containers(obj):
            for source in container.get("envFrom") or []:
                for field, known in (("configMapRef", config_maps), ("secretRef", secrets)):
                    name = _get(source, field, "name")
                    if name and name not in known:
                        issues.append(
                            Issue(
                                level="warning",
                                code="dangling-reference",
                                message=(
                                    f"Container '{container.get('name', '?')}' reads from "
                                    f"{field} '{name}', which is not part of this bundle."
                                ),
                                path=["spec", "template", "spec", "containers"],
                                object_index=index,
                            )
                        )
        template = pod_template(obj) or {}
        for volume in _get(template, "spec", "volumes", default=[]) or []:
            name = _get(volume, "configMap", "name")
            if name and name not in config_maps:
                issues.append(
                    Issue(
                        level="warning",
                        code="dangling-reference",
                        message=f"Volume references ConfigMap '{name}', not in this bundle.",
                        path=["spec", "template", "spec", "volumes"],
                        object_index=index,
                    )
                )
            secret_name = _get(volume, "secret", "secretName")
            if secret_name and secret_name not in secrets:
                issues.append(
                    Issue(
                        level="warning",
                        code="dangling-reference",
                        message=f"Volume references Secret '{secret_name}', not in this bundle.",
                        path=["spec", "template", "spec", "volumes"],
                        object_index=index,
                    )
                )
            claim_name = _get(volume, "persistentVolumeClaim", "claimName")
            if claim_name and claim_name not in claims:
                issues.append(
                    Issue(
                        level="warning",
                        code="dangling-reference",
                        message=(
                            f"Volume references PersistentVolumeClaim '{claim_name}', "
                            f"not in this bundle."
                        ),
                        path=["spec", "template", "spec", "volumes"],
                        object_index=index,
                    )
                )
    return issues


def _check_ingress_backends(
    objects: list[dict[str, Any]], services: list[dict[str, Any]]
) -> list[Issue]:
    """An Ingress backend must point at a Service that exists."""
    issues: list[Issue] = []
    service_map = {_name(service): service for service in services}
    for index, obj in enumerate(objects):
        if obj.get("kind") != "Ingress":
            continue
        for rule_index, rule in enumerate(_get(obj, "spec", "rules", default=[]) or []):
            paths = _get(rule, "http", "paths", default=[]) or []
            for path_index, http_path in enumerate(paths):
                backend = _get(http_path, "backend", "service")
                if not isinstance(backend, dict):
                    continue
                name = backend.get("name")
                if not name:
                    continue
                if not service_map:
                    # The bundle contains no Service, so the backend may well exist
                    # in the cluster.  The bundle is not the cluster.
                    continue
                service = service_map.get(name)
                if service is None:
                    issues.append(
                        Issue(
                            level="error",
                            code="ingress-backend-missing",
                            message=f"Ingress backend references unknown Service '{name}'.",
                            path=[
                                "spec",
                                "rules",
                                str(rule_index),
                                "http",
                                "paths",
                                str(path_index),
                                "backend",
                                "service",
                                "name",
                            ],
                            object_index=index,
                        )
                    )
                    continue
                port = _get(backend, "port", "number")
                service_ports = {
                    entry.get("port") for entry in _get(service, "spec", "ports", default=[]) or []
                }
                if port is not None and service_ports and port not in service_ports:
                    issues.append(
                        Issue(
                            level="error",
                            code="ingress-backend-port-missing",
                            message=(
                                f"Ingress backend references Service '{name}' on port "
                                f"{port}, but that Service does not expose it."
                            ),
                            path=[
                                "spec",
                                "rules",
                                str(rule_index),
                                "http",
                                "paths",
                                str(path_index),
                                "backend",
                                "service",
                                "port",
                                "number",
                            ],
                            object_index=index,
                        )
                    )
    return issues


def _check_scalers(objects: list[dict[str, Any]], workloads: list[dict[str, Any]]) -> list[Issue]:
    """A HorizontalPodAutoscaler must target a workload that exists.

    As with the other cross-object rules, a scaler whose target is simply absent
    from the bundle is not a finding: the workload may already be running in the
    cluster.  It becomes a finding when the bundle *does* contain workloads and
    none of them is the one being scaled.
    """
    issues: list[Issue] = []
    if not workloads:
        return issues
    targets = {(obj.get("kind"), _name(obj)) for obj in workloads}
    for index, obj in enumerate(objects):
        if obj.get("kind") != "HorizontalPodAutoscaler":
            continue
        target = _get(obj, "spec", "scaleTargetRef", default={}) or {}
        kind = target.get("kind")
        name = target.get("name")
        if not kind or not name:
            continue
        if (kind, name) not in targets:
            issues.append(
                Issue(
                    level="warning",
                    code="scaler-target-missing",
                    message=(
                        f"HorizontalPodAutoscaler targets {kind}/{name}, which is not "
                        f"part of this bundle."
                    ),
                    path=["spec", "scaleTargetRef"],
                    object_index=index,
                )
            )
    return issues


def _check_disruption_budgets(
    objects: list[dict[str, Any]], workloads: list[dict[str, Any]]
) -> list[Issue]:
    """A PodDisruptionBudget that selects nothing protects nothing.

    A budget whose selector matches no pod lets every pod be evicted at once, which
    is the opposite of what it was written to do — and it does so silently.
    """
    issues: list[Issue] = []
    if not workloads:
        return issues
    for index, obj in enumerate(objects):
        if obj.get("kind") != "PodDisruptionBudget":
            continue
        selector = _get(obj, "spec", "selector", "matchLabels", default={}) or {}
        if not selector:
            continue
        matched = any(
            all(template_labels(workload).get(key) == value for key, value in selector.items())
            for workload in workloads
        )
        if not matched:
            issues.append(
                Issue(
                    level="warning",
                    code="pdb-selector-unmatched",
                    message=(
                        f"PodDisruptionBudget selects "
                        f"{_format_selector(selector)} but no workload in this bundle "
                        f"carries those labels, so it protects nothing."
                    ),
                    path=["spec", "selector", "matchLabels"],
                    object_index=index,
                )
            )
    return issues


def _check_bindings(objects: list[dict[str, Any]]) -> list[Issue]:
    """A binding needs a role and a subject that exist.

    A ``RoleBinding`` whose ``roleRef`` names a Role that is not there is accepted
    by the API server and grants nothing at all — which is a silent failure, not an
    error.
    """
    issues: list[Issue] = []
    roles = {_name(obj) for obj in objects if obj.get("kind") in ("Role", "ClusterRole")}
    accounts = {_name(obj) for obj in objects if obj.get("kind") == "ServiceAccount"}

    for index, obj in enumerate(objects):
        kind = obj.get("kind")
        if kind not in ("RoleBinding", "ClusterRoleBinding"):
            continue
        code = (
            "role-binding-ref-missing"
            if kind == "RoleBinding"
            else "cluster-role-binding-ref-missing"
        )
        role_ref = _get(obj, "roleRef", default={}) or {}
        role_name = role_ref.get("name")
        if role_name and roles and role_name not in roles:
            issues.append(
                Issue(
                    level="warning",
                    code=code,
                    message=(
                        f"{kind} grants role '{role_name}', which is not part of this "
                        f"bundle. The binding grants nothing until that role exists."
                    ),
                    path=["roleRef", "name"],
                    object_index=index,
                )
            )
        for subject_index, subject in enumerate(_get(obj, "subjects", default=[]) or []):
            if not isinstance(subject, dict):
                continue
            if subject.get("kind") != "ServiceAccount":
                continue
            subject_name = subject.get("name")
            if subject_name and accounts and subject_name not in accounts:
                issues.append(
                    Issue(
                        level="warning",
                        code=code,
                        message=(
                            f"{kind} grants to ServiceAccount '{subject_name}', which "
                            f"is not part of this bundle."
                        ),
                        path=["subjects", str(subject_index), "name"],
                        object_index=index,
                    )
                )
    return issues


def _check_namespaces(objects: list[dict[str, Any]]) -> list[Issue]:
    """Objects in one file should agree on their namespace.

    ``kubectl apply -f`` sends every document to whichever namespace the current
    context points at, unless each object names one.  A bundle where only some objects
    carry ``metadata.namespace`` is therefore ambiguous, and a bundle where two objects
    name different namespaces cannot be applied in one go without splitting it.
    """
    issues: list[Issue] = []
    explicit: dict[str, list[int]] = {}
    implicit: list[int] = []
    for index, obj in enumerate(objects):
        namespace = _get(obj, "metadata", "namespace")
        if namespace:
            explicit.setdefault(namespace, []).append(index)
        else:
            implicit.append(index)

    if len(explicit) > 1:
        for namespace, indexes in explicit.items():
            others = sorted(other for other in explicit if other != namespace)
            for index in indexes:
                issues.append(
                    Issue(
                        level="warning",
                        code="namespace-mismatch",
                        message=(
                            f"{obj_kind(objects, index)} is in namespace '{namespace}' "
                            f"while another object in this bundle is in "
                            f"'{', '.join(others)}'. A single apply cannot span "
                            f"namespaces."
                        ),
                        path=["metadata", "namespace"],
                        object_index=index,
                    )
                )
    elif explicit and implicit:
        namespace = next(iter(explicit))
        for index in implicit:
            issues.append(
                Issue(
                    level="warning",
                    code="namespace-mismatch",
                    message=(
                        f"{obj_kind(objects, index)} has no namespace while another "
                        f"object in this bundle names '{namespace}'. "
                        f"'kubectl apply -f' sends unqualified objects to the current "
                        f"context's namespace, which may not be the one you meant."
                    ),
                    path=["metadata", "namespace"],
                    object_index=index,
                )
            )
    return issues


def obj_kind(objects: list[dict[str, Any]], index: int) -> str:
    """Kind name of an object in the bundle, for use in a message."""
    if 0 <= index < len(objects):
        return str(objects[index].get("kind", "object"))
    return "object"


def _check_container_hygiene(workloads: list[dict[str, Any]]) -> list[Issue]:
    """Advice that catches the small omissions which cause trouble later."""
    issues: list[Issue] = []
    for index, workload in enumerate(workloads):
        for container in containers(workload):
            name = container.get("name", "?")
            image = container.get("image")
            if image and not _has_tag(image):
                issues.append(
                    Issue(
                        level="warning",
                        code="image-no-tag",
                        message=(
                            f"Container '{name}' uses image '{image}' with no tag, so it "
                            f"resolves to :latest. Pin a tag or a digest."
                        ),
                        path=["spec", "template", "spec", "containers"],
                        object_index=index,
                    )
                )
            if (
                workload.get("kind") in PROBE_EXPECTED
                and not container.get("livenessProbe")
                and not container.get("readinessProbe")
            ):
                issues.append(
                    Issue(
                        level="warning",
                        code="no-probe",
                        message=(
                            f"Container '{name}' has no liveness or readiness "
                            f"probe. Kubernetes cannot tell whether it is healthy."
                        ),
                        path=["spec", "template", "spec", "containers"],
                        object_index=index,
                    )
                )
            resources = container.get("resources") or {}
            limits = resources.get("limits") or {}
            requests = resources.get("requests") or {}
            if limits and not requests:
                issues.append(
                    Issue(
                        level="warning",
                        code="limit-without-request",
                        message=(
                            f"Container '{name}' sets resource limits but no requests. "
                            f"The scheduler will place it using the limit, which is "
                            f"usually not what you want."
                        ),
                        path=["spec", "template", "spec", "containers"],
                        object_index=index,
                    )
                )
    return issues


def _format_selector(selector: dict[str, str]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(selector.items()))
