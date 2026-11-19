"""Cross-object semantics — the layer that a schema cannot express.

A Kubernetes schema checks one object in isolation.  It therefore cannot notice the
failure that actually bites in practice: a Deployment and a Service that each look
perfectly valid but do not agree with each other.  The Deployment deploys, the Service
is created, and nothing routes because the selector does not match the pod labels.

The rules below encode the agreements Kubernetes expects between objects.
"""

from __future__ import annotations

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
    """A Service selector must match the pods it is meant to route to."""
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
            issues.append(
                Issue(
                    level="warning",
                    code="service-selector-unverifiable",
                    message=(
                        f"Service {_name(service)} selects "
                        f"{_format_selector(selector)} but no workload is part of this "
                        f"bundle, so the match cannot be checked here."
                    ),
                    path=["spec", "selector"],
                    object_index=index,
                )
            )
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
                    issues.append(
                        Issue(
                            level="warning",
                            code="ingress-backend-unverifiable",
                            message=(
                                f"Ingress backend '{name}' cannot be checked: no "
                                f"Service is part of this bundle."
                            ),
                            path=["spec", "rules", str(rule_index)],
                            object_index=index,
                        )
                    )
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
    """A HorizontalPodAutoscaler must target a workload that exists."""
    issues: list[Issue] = []
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
