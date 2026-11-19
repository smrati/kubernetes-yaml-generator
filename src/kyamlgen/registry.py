"""Per-kind metadata the schema does not carry.

The Kubernetes OpenAPI schema describes *shape* — field names, types, required-ness.
It does not say whether a resource is namespaced, what its plural is, or which
controller normally creates it.  That information decides how the form should behave,
so it lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .schemas import KindRef

#: Kinds that live outside any namespace.
CLUSTER_SCOPED = {
    "APIGroup",
    "APIGroupList",
    "APIResourceList",
    "APIVersions",
    "APIService",
    "CSIDriver",
    "CSINode",
    "CertificateSigningRequest",
    "ClusterRole",
    "ClusterRoleBinding",
    "ClusterTrustBundle",
    "ComponentStatus",
    "ComponentStatusList",
    "CustomResourceDefinition",
    "FlowSchema",
    "IngressClass",
    "MutatingWebhookConfiguration",
    "Namespace",
    "Node",
    "PersistentVolume",
    "PodSecurityPolicy",
    "PriorityClass",
    "PriorityLevelConfiguration",
    "RuntimeClass",
    "SelfSubjectAccessReview",
    "SelfSubjectRulesReview",
    "StorageClass",
    "StorageVersion",
    "SubjectAccessReview",
    "TokenReview",
    "ValidatingAdmissionPolicy",
    "ValidatingAdmissionPolicyBinding",
    "ValidatingWebhookConfiguration",
    "VolumeAttachment",
}

#: Kinds a controller normally owns.  A human authoring one of these is taking over
#: the controller's job, which is a legitimate choice but worth warning about.
OWNED_BY_CONTROLLER: dict[str, str] = {
    "Pod": "a Deployment, StatefulSet, DaemonSet, Job or ReplicaSet",
    "ReplicaSet": "a Deployment",
    "ControllerRevision": "a StatefulSet or DaemonSet",
    "Endpoints": "a Service",
    "EndpointSlice": "the EndpointSlice controller",
    "Event": "the kubelet or the API server",
    "Lease": "a node's kubelet or a leader-election client",
    "HorizontalPodAutoscaler": "the autoscaler",
    "PodDisruptionBudget": "the disruption controller",
    "TokenReview": "the API server",
    "SubjectAccessReview": "the API server",
    "SelfSubjectAccessReview": "the API server",
    "ComponentStatus": "the kubelet",
    "Node": "the kubelet",
    "ResourceClaim": "the resource scheduler",
}

#: Kinds that are never usefully authored by hand.
NOT_AUTHORABLE = {
    "Node": "The kubelet registers and owns Nodes. A hand-written Node manifest is "
    "rejected in practice and tells you nothing about deploying workloads.",
    "ComponentStatus": "Read-only projection of component health, filled in by the API server.",
    "SelfSubjectAccessReview": "A request, not a resource you own.",
    "SubjectAccessReview": "A request, not a resource you own.",
    "SelfSubjectRulesReview": "A request, not a resource you own.",
    "TokenReview": "A request, not a resource you own.",
}

#: Irregular plurals.  Everything else follows the regular rules below.
IRREGULAR_PLURALS: dict[str, str] = {
    "Endpoints": "endpoints",
    "Ingress": "ingresses",
    "NetworkPolicy": "networkpolicies",
    "PodSecurityPolicy": "podsecuritypolicies",
    "PriorityClass": "priorityclasses",
    "StorageClass": "storageclasses",
    "IngressClass": "ingressclasses",
    "RuntimeClass": "runtimeclasses",
    "GatewayClass": "gatewayclasses",
    "ComponentStatus": "componentstatuses",
    "CustomResourceDefinition": "customresourcedefinitions",
    "ClusterTrustBundle": "clustertrustbundles",
    "FlowSchema": "flowschemas",
    "PriorityLevelConfiguration": "prioritylevelconfigurations",
    "ValidatingAdmissionPolicy": "validatingadmissionpolicies",
    "VolumeAttachment": "volumeattachments",
    "CSIDriver": "csidrivers",
    "CSINode": "csinodes",
    "APIService": "apiservices",
    "Lease": "leases",
}


def pluralise(kind: str) -> str:
    """Plural resource name for a kind."""
    if kind in IRREGULAR_PLURALS:
        return IRREGULAR_PLURALS[kind]
    lowered = kind.lower()
    if lowered.endswith(("s", "x", "z", "ch", "sh")):
        return lowered + "es"
    if lowered.endswith("y") and len(lowered) > 1 and lowered[-2] not in "aeiou":
        return lowered[:-1] + "ies"
    return lowered + "s"


@dataclass(frozen=True)
class KindInfo:
    """Everything the UI needs to know about one kind."""

    group: str
    version: str
    kind: str
    api_version: str
    plural: str
    namespaced: bool
    owner: str | None = None
    authorable: bool = True
    note: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def key(self) -> str:
        """Stable identifier used in URLs and form payloads."""
        return f"{self.api_version}/{self.kind}"


#: Coarse grouping used to organise the kind picker.
CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "Workloads",
        (
            "Deployment",
            "StatefulSet",
            "DaemonSet",
            "ReplicaSet",
            "Pod",
            "Job",
            "CronJob",
            "ReplicationController",
        ),
    ),
    (
        "Networking",
        (
            "Service",
            "Ingress",
            "IngressClass",
            "NetworkPolicy",
            "EndpointSlice",
            "Gateway",
            "GatewayClass",
            "HTTPRoute",
        ),
    ),
    (
        "Configuration",
        ("ConfigMap", "Secret", "Namespace", "ServiceAccount", "ResourceQuota", "LimitRange"),
    ),
    ("Storage", ("PersistentVolume", "PersistentVolumeClaim", "StorageClass", "VolumeAttachment")),
    ("Scaling", ("HorizontalPodAutoscaler", "PodDisruptionBudget", "PriorityClass")),
    ("Cluster", ("Node", "RuntimeClass", "ComponentStatus", "CSIDriver", "CSINode")),
    (
        "Access control",
        (
            "Role",
            "RoleBinding",
            "ClusterRole",
            "ClusterRoleBinding",
            "ServiceAccount",
            "PodSecurityPolicy",
        ),
    ),
    (
        "Admission & policy",
        (
            "MutatingWebhookConfiguration",
            "ValidatingWebhookConfiguration",
            "ValidatingAdmissionPolicy",
            "ValidatingAdmissionPolicyBinding",
            "PodDisruptionBudget",
        ),
    ),
]


def category_for(kind: str) -> str:
    """Category name for a kind."""
    for category, kinds in CATEGORY_RULES:
        if kind in kinds:
            return category
    return "Other"


def describe(ref: KindRef) -> KindInfo:
    """Build the :class:`KindInfo` for a schema-discovered kind."""
    namespaced = ref.kind not in CLUSTER_SCOPED
    owner = OWNED_BY_CONTROLLER.get(ref.kind)
    note = NOT_AUTHORABLE.get(ref.kind, "")
    if owner and ref.kind not in NOT_AUTHORABLE:
        note = (
            f"Normally created by {owner}. Authoring it directly means taking over "
            f"that controller's job."
        )
    return KindInfo(
        group=ref.group,
        version=ref.version,
        kind=ref.kind,
        api_version=ref.api_version,
        plural=pluralise(ref.kind),
        namespaced=namespaced,
        owner=owner,
        authorable=ref.kind not in NOT_AUTHORABLE,
        note=note,
        tags=(category_for(ref.kind),),
    )
