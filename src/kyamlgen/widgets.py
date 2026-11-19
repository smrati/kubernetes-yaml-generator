"""Turn a Kubernetes JSON schema into a form widget tree.

The tree is plain JSON so the browser can render it directly; there is no
server-side HTML rendering of the form and therefore no second implementation of the
widget rules to keep in sync.

A node looks like::

    {
      "id": "w12",
      "name": "image",
      "path": ["spec", "template", "spec", "containers", "*", "image"],
      "kind": "string",
      "label": "Image",
      "description": "Container image name...",
      "required": true,
      "advanced": false,
      ...
    }

``kind`` is one of ``string``, ``text``, ``integer``, ``number``, ``boolean``,
``select``, ``quantity``, ``int-or-string``, ``datetime``, ``object``, ``array``,
``map`` or ``json``.
"""

from __future__ import annotations

from typing import Any

from .schemas import (
    DEFS_INT_OR_STRING,
    DEFS_OBJECT_META,
    DEFS_QUANTITY,
    SchemaBundle,
)

#: ObjectMeta fields the API server owns.  A human authoring a manifest should never
#: set these, and offering them is an invitation to produce rejected manifests.
SERVER_MANAGED_METADATA = {
    "creationTimestamp",
    "deletionGracePeriodSeconds",
    "deletionTimestamp",
    "generation",
    "managedFields",
    "resourceVersion",
    "selfLink",
    "uid",
}

#: ObjectMeta fields that are legitimate but rarely wanted; shown behind "advanced".
RARE_METADATA = {"finalizers", "ownerReferences"}

#: Per-definition sets of properties shown by default.  Everything else in that
#: definition is folded away behind "advanced".  A definition with no entry here shows
#: all of its properties.
#:
#: This is an allow-list on purpose.  The Kubernetes schema keeps growing — v1.37
#: already carries alpha fields like ``evictionResponders`` and ``hostnameOverride`` —
#: and a denylist would surface every new field to somebody who just wants to set an
#: image.
COMMON_PROPERTIES: dict[str, set[str]] = {
    "io.k8s.api.core.v1.PodSpec": {
        "containers",
        "initContainers",
        "volumes",
        "restartPolicy",
        "serviceAccountName",
        "nodeSelector",
        "imagePullSecrets",
    },
    "io.k8s.api.core.v1.Container": {
        "name",
        "image",
        "command",
        "args",
        "ports",
        "env",
        "envFrom",
        "resources",
        "volumeMounts",
        "imagePullPolicy",
        "livenessProbe",
        "readinessProbe",
    },
    "io.k8s.api.apps.v1.DeploymentSpec": {"replicas", "selector", "template"},
    "io.k8s.api.apps.v1.StatefulSetSpec": {
        "replicas",
        "selector",
        "template",
        "serviceName",
        "podManagementPolicy",
        "volumeClaimTemplates",
    },
    "io.k8s.api.apps.v1.DaemonSetSpec": {"selector", "template"},
    "io.k8s.api.apps.v1.ReplicaSetSpec": {"replicas", "selector", "template"},
    "io.k8s.api.core.v1.ServiceSpec": {
        "type",
        "selector",
        "ports",
        "clusterIP",
        "externalName",
    },
    "io.k8s.api.core.v1.ContainerPort": {"name", "containerPort", "protocol", "hostPort"},
    "io.k8s.api.core.v1.ServicePort": {"name", "port", "targetPort", "nodePort", "protocol"},
    "io.k8s.api.core.v1.EnvVar": {"name", "value", "valueFrom"},
    "io.k8s.api.core.v1.VolumeMount": {"name", "mountPath", "subPath", "readOnly"},
    "io.k8s.api.core.v1.Volume": {
        "name",
        "configMap",
        "secret",
        "persistentVolumeClaim",
        "emptyDir",
        "hostPath",
        "projected",
    },
    "io.k8s.api.core.v1.ResourceRequirements": {"limits", "requests"},
    "io.k8s.api.core.v1.PersistentVolumeClaimSpec": {
        "accessModes",
        "resources",
        "storageClassName",
        "volumeName",
        "volumeMode",
    },
    "io.k8s.api.core.v1.PodTemplateSpec": {"metadata", "spec"},
    "io.k8s.api.networking.v1.IngressSpec": {"ingressClassName", "defaultBackend", "tls", "rules"},
    "io.k8s.api.networking.v1.IngressRule": {"host", "http"},
    "io.k8s.api.networking.v1.HTTPIngressRuleValue": {"paths"},
    "io.k8s.api.networking.v1.HTTPIngressPath": {"path", "pathType", "backend"},
    "io.k8s.api.networking.v1.IngressBackend": {"service", "resource"},
    "io.k8s.api.networking.v1.IngressServiceBackend": {"name", "port"},
    "io.k8s.api.networking.v1.ServiceBackendPort": {"name", "number"},
    "io.k8s.api.batch.v1.JobSpec": {
        "template",
        "parallelism",
        "completions",
        "backoffLimit",
        "ttlSecondsAfterFinished",
    },
    "io.k8s.api.batch.v1.CronJobSpec": {
        "schedule",
        "timeZone",
        "concurrencyPolicy",
        "jobTemplate",
        "suspend",
    },
    "io.k8s.api.autoscaling.v2.HorizontalPodAutoscalerSpec": {
        "scaleTargetRef",
        "minReplicas",
        "maxReplicas",
        "metrics",
    },
    "io.k8s.api.autoscaling.v2.MetricSpec": {"type", "resource", "pods", "object", "external"},
    "io.k8s.api.policy.v1.PodDisruptionBudgetSpec": {"minAvailable", "maxUnavailable", "selector"},
    "io.k8s.api.policy.v1.PodDisruptionBudgetStatus": set(),
}

#: Properties that are never shown.  Deprecated aliases and fields the API server
#: populates on its own have no place in an authoring form.
HIDDEN_PROPERTIES: dict[str, set[str]] = {
    "io.k8s.api.core.v1.PodSpec": {"serviceAccount"},
}

#: Fields the API schema does not mark required but that Kubernetes needs in practice.
#: A container with no image is accepted by the API server and then never starts.
EXTRA_REQUIRED: dict[str, set[str]] = {
    "io.k8s.api.core.v1.Container": {"image"},
    "io.k8s.api.core.v1.ServicePort": {"port"},
    "io.k8s.api.networking.v1.IngressServiceBackend": {"name"},
}

#: Enum values the schema does not carry.
#:
#: The bundled OpenAPI schemas describe field *types*, not permitted values — there is
#: not a single ``enum`` anywhere in the bundle.  That means a typo such as
#: ``type: ClustrIP`` passes every schema check and is only rejected later by the API
#: server.  These tables restore the information the schema dropped.
FIELD_ENUMS: dict[tuple[str, str], list[str]] = {
    ("io.k8s.api.core.v1.Container", "imagePullPolicy"): [
        "Always",
        "IfNotPresent",
        "Never",
    ],
    ("io.k8s.api.core.v1.Container", "terminationMessagePolicy"): [
        "File",
        "FallbackToLogsOnError",
    ],
    ("io.k8s.api.core.v1.ContainerPort", "protocol"): ["TCP", "UDP", "SCTP"],
    ("io.k8s.api.core.v1.ServicePort", "protocol"): ["TCP", "UDP", "SCTP"],
    ("io.k8s.api.core.v1.ServiceSpec", "type"): [
        "ClusterIP",
        "NodePort",
        "LoadBalancer",
        "ExternalName",
    ],
    ("io.k8s.api.core.v1.ServiceSpec", "externalTrafficPolicy"): ["Cluster", "Local"],
    ("io.k8s.api.core.v1.ServiceSpec", "internalTrafficPolicy"): ["Cluster", "Local"],
    ("io.k8s.api.core.v1.ServiceSpec", "sessionAffinity"): ["None", "ClientIP"],
    ("io.k8s.api.core.v1.ServiceSpec", "ipFamilyPolicy"): [
        "SingleStack",
        "PreferDualStack",
        "RequireDualStack",
    ],
    ("io.k8s.api.core.v1.ServiceSpec", "trafficDistribution"): [
        "PreferClose",
        "PreferSameNode",
    ],
    ("io.k8s.api.core.v1.PodSpec", "restartPolicy"): ["Always", "OnFailure", "Never"],
    ("io.k8s.api.core.v1.PodSpec", "dnsPolicy"): [
        "ClusterFirst",
        "ClusterFirstWithHostNet",
        "Default",
        "None",
    ],
    ("io.k8s.api.core.v1.PodSpec", "preemptionPolicy"): [
        "Never",
        "PreemptLowerPriority",
    ],
    ("io.k8s.api.core.v1.PodSpec", "schedulerName"): ["default-scheduler"],
    ("io.k8s.api.core.v1.PersistentVolumeClaimSpec", "volumeMode"): [
        "Filesystem",
        "Block",
    ],
    ("io.k8s.api.core.v1.PersistentVolumeSpec", "volumeMode"): ["Filesystem", "Block"],
    ("io.k8s.api.core.v1.Volume", "emptyDir"): [],
    ("io.k8s.api.networking.v1.HTTPIngressPath", "pathType"): [
        "Exact",
        "Prefix",
        "ImplementationSpecific",
    ],
    ("io.k8s.api.batch.v1.CronJobSpec", "concurrencyPolicy"): [
        "Allow",
        "Forbid",
        "Replace",
    ],
    ("io.k8s.api.batch.v1.JobSpec", "completionMode"): ["NonIndexed", "Indexed"],
    ("io.k8s.api.batch.v1.JobSpec", "podReplacementPolicy"): [
        "TerminatingOrFailed",
        "Failed",
    ],
    ("io.k8s.api.apps.v1.DeploymentStrategy", "type"): ["Recreate", "RollingUpdate"],
    ("io.k8s.api.apps.v1.StatefulSetUpdateStrategy", "type"): [
        "RollingUpdate",
        "OnDelete",
    ],
    ("io.k8s.api.apps.v1.DaemonSetUpdateStrategy", "type"): [
        "RollingUpdate",
        "OnDelete",
    ],
    ("io.k8s.api.autoscaling.v2.MetricSpec", "type"): [
        "Object",
        "Pods",
        "Resource",
        "External",
        "ContainerResource",
    ],
    ("io.k8s.api.core.v1.Secret", "type"): [
        "Opaque",
        "kubernetes.io/tls",
        "kubernetes.io/dockerconfigjson",
        "kubernetes.io/dockercfg",
        "kubernetes.io/basic-auth",
        "kubernetes.io/ssh-auth",
        "kubernetes.io/service-account-token",
        "bootstrap.kubernetes.io/token",
    ],
    ("io.k8s.api.core.v1.ConditionStatus", "status"): ["True", "False", "Unknown"],
}

#: Enum values for the *items* of an array field.
ITEM_ENUMS: dict[tuple[str, str], list[str]] = {
    ("io.k8s.api.core.v1.PersistentVolumeClaimSpec", "accessModes"): [
        "ReadWriteOnce",
        "ReadOnlyMany",
        "ReadWriteMany",
        "ReadWriteOncePod",
    ],
    ("io.k8s.api.core.v1.PersistentVolumeSpec", "accessModes"): [
        "ReadWriteOnce",
        "ReadOnlyMany",
        "ReadWriteMany",
        "ReadWriteOncePod",
    ],
    ("io.k8s.api.core.v1.ServiceSpec", "ipFamilies"): ["IPv4", "IPv6"],
}

#: Friendly labels for fields whose names do not read well when title-cased.
LABEL_OVERRIDES: dict[str, str] = {
    "name": "Name",
    "namespace": "Namespace",
    "labels": "Labels",
    "annotations": "Annotations",
    "image": "Image",
    "imagePullPolicy": "Image pull policy",
    "command": "Command",
    "args": "Args",
    "env": "Environment",
    "envFrom": "Environment from",
    "ports": "Ports",
    "resources": "Resources",
    "replicas": "Replicas",
    "selector": "Selector",
    "matchLabels": "Match labels",
    "matchExpressions": "Match expressions",
    "template": "Pod template",
    "serviceAccountName": "Service account name",
    "targetPort": "Target port",
    "nodePort": "Node port",
    "containerPort": "Container port",
    "hostPort": "Host port",
    "protocol": "Protocol",
    "type": "Type",
    "storageClassName": "Storage class",
    "accessModes": "Access modes",
    "data": "Data",
    "stringData": "String data",
    "kind": "Kind",
    "apiVersion": "API version",
    "spec": "Spec",
    "status": "Status",
}

#: Field-name suffix -> (minimum, maximum) range.  The Kubernetes OpenAPI schema
#: carries no numeric bounds, so these come from the API documentation instead.
FIELD_RANGES: dict[str, tuple[int, int]] = {
    "port": (1, 65535),
    "targetPort": (1, 65535),
    "containerPort": (1, 65535),
    "hostPort": (1, 65535),
    "nodePort": (30000, 32767),
    "healthCheckNodePort": (30000, 32767),
}

#: Field-name suffix -> minimum only.
FIELD_MINIMUMS: dict[str, int] = {
    "replicas": 0,
    "minReadySeconds": 0,
    "revisionHistoryLimit": 0,
    "progressDeadlineSeconds": 0,
    "maxSurge": 0,
    "maxUnavailable": 0,
    "terminationGracePeriodSeconds": 0,
    "backoffLimit": 0,
    "completions": 0,
    "parallelism": 0,
    "concurrencyPolicy": 0,
    "terminationGracePeriodSeconds ": 0,
}

_ID_SEGMENT = "*"


class _Counter:
    """Monotonic id source, so every widget in a tree has a unique DOM id."""

    def __init__(self) -> None:
        self._value = 0

    def next(self) -> str:
        self._value += 1
        return f"w{self._value}"


def _types_of(alternative: Any) -> set[str]:
    """Collect the JSON types an ``oneOf``/``anyOf`` alternative allows."""
    if not isinstance(alternative, dict):
        return set()
    declared = alternative.get("type")
    if isinstance(declared, str):
        return {declared}
    if isinstance(declared, list):
        return set(declared)
    return set()


def _primary_type(node: dict[str, Any]) -> str | None:
    """The non-null type of a schema node, if it declares one."""
    declared = node.get("type")
    if isinstance(declared, str):
        return declared
    if isinstance(declared, list):
        for candidate in declared:
            if candidate != "null":
                return candidate
        return "null"
    return None


def _title(name: str) -> str:
    """Turn ``imagePullPolicy`` into ``Image pull policy``."""
    if name in LABEL_OVERRIDES:
        return LABEL_OVERRIDES[name]
    out: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index > 0 and not name[index - 1].isupper():
            out.append(" ")
        out.append(char.lower() if index else char.upper())
    return "".join(out)


def _range_for(field_name: str) -> tuple[int | None, int | None]:
    if field_name in FIELD_RANGES:
        low, high = FIELD_RANGES[field_name]
        return low, high
    if field_name in FIELD_MINIMUMS:
        return FIELD_MINIMUMS[field_name], None
    return None, None


def _map_style(path: list[str]) -> str:
    """Which rules apply to a map's keys and values.

    Label values are restricted to 63 characters of a limited character set, annotation
    values are arbitrary strings, and a generic map like ``ConfigMap.data`` has no
    Kubernetes-level restrictions at all.
    """
    if len(path) >= 2 and path[-2] == "metadata" and path[-1] in ("labels", "annotations"):  # noqa: PLR2004
        return path[-1]
    return "generic"


class WidgetBuilder:
    """Builds a widget tree for one kind."""

    def __init__(self, bundle: SchemaBundle) -> None:
        self.bundle = bundle
        self._ids = _Counter()
        # Definition names currently being expanded.  A few schemas are genuinely
        # self-referential — a CustomResourceDefinition embeds a JSONSchemaProps which
        # embeds another JSONSchemaProps — so the walk needs a cycle guard.
        self._def_stack: list[str] = []

    # -- entry point ---------------------------------------------------------

    def build(self, kind: str, api_version: str) -> dict[str, Any]:
        schema = self.bundle.kind_schema(kind, api_version)
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or [])

        children: list[dict[str, Any]] = []
        for name, node in properties.items():
            if name in ("apiVersion", "kind", "status"):
                continue
            children.append(
                self._build_property(
                    node,
                    name=name,
                    path=[name],
                    required=name in required,
                    parent_def=None,
                )
            )

        return {
            "id": "root",
            "name": "",
            "path": [],
            "kind": "object",
            "label": "",
            "description": schema.get("description", ""),
            "required": True,
            "advanced": False,
            "children": children,
        }

    # -- node construction ---------------------------------------------------

    def _build_property(  # noqa: PLR0911, PLR0912, PLR0915
        self,
        node: Any,
        *,
        name: str,
        path: list[str],
        required: bool,
        parent_def: str | None,
    ) -> dict[str, Any]:
        def_name = self.bundle.definition_name(node)
        resolved = self.bundle.resolve(node)
        if not isinstance(resolved, dict):
            resolved = {}

        widget: dict[str, Any] = {
            "id": self._ids.next(),
            "name": name,
            "path": path,
            "kind": "json",
            "label": _title(name),
            "description": resolved.get("description", "") or "",
            "required": required,
            "advanced": False,
        }

        # Definitions that deserve a dedicated widget.
        if def_name == DEFS_INT_OR_STRING:
            widget["kind"] = "int-or-string"
            widget["placeholder"] = "8080 or http"
            return widget
        if def_name == DEFS_QUANTITY:
            widget["kind"] = "quantity"
            widget["placeholder"] = "500m / 128Mi"
            return widget

        # Objects with no properties of their own are free-form.
        declared_type = _primary_type(resolved)
        alternatives = resolved.get("oneOf") or resolved.get("anyOf")
        if declared_type is None and alternatives:
            candidate_types: set[str] = set()
            for alternative in alternatives:
                candidate_types |= _types_of(alternative)
            candidate_types.discard("null")
            if candidate_types == {"string", "integer"}:
                widget["kind"] = "int-or-string"
                return widget
            if candidate_types == {"string", "number"}:
                widget["kind"] = "quantity"
                return widget
            if len(candidate_types) == 1:
                declared_type = next(iter(candidate_types))
            else:
                widget["kind"] = "json"
                widget["placeholder"] = "JSON"
                return widget

        enum_values = resolved.get("enum")
        if enum_values:
            widget["kind"] = "select"
            widget["enum"] = list(enum_values)
            widget["default"] = resolved.get("default")
            return widget

        if declared_type == "object":
            properties = resolved.get("properties") or {}
            additional = resolved.get("additionalProperties")
            if properties:
                if def_name == DEFS_OBJECT_META:
                    widget["kind"] = "object"
                    widget["children"] = self._build_object_meta(properties, resolved, path)
                    widget["label"] = "Metadata"
                    widget["collapsed"] = False
                    return widget
                if def_name is not None and def_name in self._def_stack:
                    # Self-referential schema: offer the raw shape instead of recursing.
                    widget["kind"] = "json"
                    widget["placeholder"] = "JSON"
                    widget["description"] = (
                        widget["description"]
                        + " This field can contain itself; it is edited as raw JSON."
                    ).strip()
                    return widget
                if def_name is not None:
                    self._def_stack.append(def_name)
                try:
                    widget["kind"] = "object"
                    widget["children"] = self._build_children(properties, resolved, path, def_name)
                finally:
                    if def_name is not None:
                        self._def_stack.pop()
                return widget
            if isinstance(additional, dict):
                widget["kind"] = "map"
                widget["valueKind"] = self._value_kind(additional)
                widget["mapStyle"] = _map_style(path)
                widget["keyPlaceholder"] = "key"
                widget["valuePlaceholder"] = "value"
                return widget
            widget["kind"] = "json"
            widget["placeholder"] = "JSON"
            return widget

        if declared_type == "array":
            items = resolved.get("items") or {}
            widget["kind"] = "array"
            widget["item"] = self._build_property(
                items,
                name=name,
                path=[*path, _ID_SEGMENT],
                required=False,
                parent_def=def_name,
            )
            item_enum = ITEM_ENUMS.get((parent_def or "", name))
            if item_enum:
                widget["item"]["kind"] = "select"
                widget["item"]["enum"] = list(item_enum)
                widget["item"]["label"] = widget["item"].get("label") or _title(name)
            list_type = resolved.get("x-kubernetes-list-type")
            if list_type:
                widget["listType"] = list_type
            list_map_keys = resolved.get("x-kubernetes-list-map-keys")
            if list_map_keys:
                widget["listMapKeys"] = list(list_map_keys)
            widget["itemLabel"] = _title(name.rstrip("s") if name.endswith("s") else name)
            return widget

        if declared_type == "boolean":
            widget["kind"] = "boolean"
            widget["default"] = resolved.get("default", False)
            return widget

        if declared_type == "integer":
            widget["kind"] = "integer"
            low, high = _range_for(name)
            if low is not None:
                widget["min"] = low
            if high is not None:
                widget["max"] = high
            widget["default"] = resolved.get("default")
            return widget

        if declared_type == "number":
            widget["kind"] = "number"
            widget["default"] = resolved.get("default")
            return widget

        if declared_type == "string":
            if resolved.get("format") == "date-time":
                widget["kind"] = "datetime"
                return widget
            widget["kind"] = "string"
            if resolved.get("pattern"):
                widget["pattern"] = resolved["pattern"]
            widget["default"] = resolved.get("default")
            widget["placeholder"] = resolved.get("default", "") or ""
            return widget

        widget["kind"] = "json"
        widget["placeholder"] = "JSON"
        return widget

    def _build_children(
        self,
        properties: dict[str, Any],
        parent: dict[str, Any],
        path: list[str],
        parent_def: str | None,
    ) -> list[dict[str, Any]]:
        required = set(parent.get("required") or [])
        required |= EXTRA_REQUIRED.get(parent_def or "", set())
        common = COMMON_PROPERTIES.get(parent_def or "")
        hidden = HIDDEN_PROPERTIES.get(parent_def or "", set())
        children = []
        for name, node in properties.items():
            if name in hidden:
                continue
            child = self._build_property(
                node,
                name=name,
                path=[*path, name],
                required=name in required,
                parent_def=parent_def,
            )
            if common is not None and name not in common:
                child["advanced"] = True
            field_enum = FIELD_ENUMS.get((parent_def or "", name))
            if field_enum:
                child["kind"] = "select"
                child["enum"] = list(field_enum)
            children.append(child)
        return children

    def _build_object_meta(
        self,
        properties: dict[str, Any],
        parent: dict[str, Any],
        path: list[str],
    ) -> list[dict[str, Any]]:
        """Metadata gets a curated field list.

        ``ObjectMeta`` has 15 fields, eight of which the API server owns.  Showing all
        of them would be noise at best and an invitation to produce rejected manifests
        at worst.
        """
        required = set(parent.get("required") or [])
        # ObjectMeta declares no required fields in the schema, but an object without a
        # name cannot be created.  A pod template's metadata is different: it is
        # identified by its labels, and a name there is unusual.
        if path == ["metadata"]:
            required.add("name")
        children: list[dict[str, Any]] = []
        for name, node in properties.items():
            if name in SERVER_MANAGED_METADATA:
                continue
            child = self._build_property(
                node,
                name=name,
                path=[*path, name],
                required=name in required,
                parent_def=DEFS_OBJECT_META,
            )
            if name in RARE_METADATA:
                child["advanced"] = True
            children.append(child)
        return children

    def _value_kind(self, additional: dict[str, Any]) -> str:  # noqa: PLR0911
        """Widget kind for the values of a free-form map.

        The map's value schema is often a ``$ref`` to a shared definition, so it has to
        be resolved before the type can be read — ``resources.limits`` is a map of
        Quantities and ``targetPort``-style fields are IntOrStrings.
        """
        definition = self.bundle.definition_name(additional)
        if definition == DEFS_QUANTITY:
            return "quantity"
        if definition == DEFS_INT_OR_STRING:
            return "int-or-string"
        resolved = self.bundle.resolve(additional)
        if not isinstance(resolved, dict):
            return "json"
        alternatives = resolved.get("oneOf") or resolved.get("anyOf")
        if alternatives:
            candidate_types: set[str] = set()
            for alternative in alternatives:
                candidate_types |= _types_of(alternative)
            candidate_types.discard("null")
            if candidate_types == {"string", "integer"}:
                return "int-or-string"
            if candidate_types == {"string", "number"}:
                return "quantity"
        additional_type = _primary_type(resolved)
        if additional_type == "string":
            return "string"
        if additional_type == "integer":
            return "integer"
        if additional_type == "boolean":
            return "boolean"
        if additional_type == "number":
            return "number"
        return "json"
