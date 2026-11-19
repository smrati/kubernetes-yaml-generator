from __future__ import annotations

from kyamlgen.schemas import load_bundle
from kyamlgen.semantics import analyse
from kyamlgen.validate import SchemaValidator, check_form
from kyamlgen.widgets import WidgetBuilder


def deployment(**overrides) -> dict:
    manifest = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "api", "labels": {"app": "api"}},
        "spec": {
            "replicas": 2,
            "selector": {"matchLabels": {"app": "api"}},
            "template": {
                "metadata": {"labels": {"app": "api"}},
                "spec": {
                    "containers": [
                        {
                            "name": "web",
                            "image": "nginx:1.27",
                            "ports": [{"name": "http", "containerPort": 8080}],
                        }
                    ]
                },
            },
        },
    }
    manifest.update(overrides)
    return manifest


def service(**overrides) -> dict:
    manifest = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": "api"},
        "spec": {
            "type": "ClusterIP",
            "selector": {"app": "api"},
            "ports": [{"name": "http", "port": 80, "targetPort": 8080}],
        },
    }
    manifest.update(overrides)
    return manifest


def codes(issues) -> set[str]:
    return {issue.code for issue in issues}


# -- form-time -------------------------------------------------------------


def test_missing_required_field_is_reported() -> None:
    tree = WidgetBuilder(load_bundle("1.31.0")).build("Deployment", "apps/v1")
    manifest = deployment()
    del manifest["metadata"]["name"]
    issues = check_form(tree, manifest)
    assert "required" in codes(issues)
    assert any(issue.path == ["metadata", "name"] for issue in issues)


def test_out_of_range_port_is_rejected() -> None:
    tree = WidgetBuilder(load_bundle("1.31.0")).build("Service", "v1")
    manifest = service()
    manifest["spec"]["ports"][0]["port"] = 70000
    issues = check_form(tree, manifest)
    assert "range" in codes(issues)


def test_invalid_object_name_is_rejected() -> None:
    tree = WidgetBuilder(load_bundle("1.31.0")).build("Deployment", "apps/v1")
    manifest = deployment()
    manifest["metadata"]["name"] = "Not_Valid"
    issues = check_form(tree, manifest)
    assert "name" in codes(issues)


def test_invalid_label_key_is_rejected() -> None:
    tree = WidgetBuilder(load_bundle("1.31.0")).build("Deployment", "apps/v1")
    manifest = deployment()
    manifest["metadata"]["labels"] = {"bad key!": "value"}
    issues = check_form(tree, manifest)
    assert "label-key" in codes(issues)


def test_quantity_syntax_is_checked() -> None:
    tree = WidgetBuilder(load_bundle("1.31.0")).build("Deployment", "apps/v1")
    manifest = deployment()
    manifest["spec"]["template"]["spec"]["containers"][0]["resources"] = {
        "limits": {"cpu": "half a core"}
    }
    issues = check_form(tree, manifest)
    assert "quantity" in codes(issues)


def test_valid_quantity_is_accepted() -> None:
    tree = WidgetBuilder(load_bundle("1.31.0")).build("Deployment", "apps/v1")
    manifest = deployment()
    manifest["spec"]["template"]["spec"]["containers"][0]["resources"] = {
        "limits": {"cpu": "500m", "memory": "128Mi"},
        "requests": {"cpu": "250m", "memory": "64Mi"},
    }
    issues = check_form(tree, manifest)
    assert not [issue for issue in issues if issue.level == "error"]


# -- JSON Schema -----------------------------------------------------------


def test_unknown_field_is_rejected_by_the_schema() -> None:
    validator = SchemaValidator(load_bundle("1.31.0"))
    manifest = deployment()
    manifest["spec"]["notAField"] = True
    issues = validator.check(manifest)
    assert any("notAField" in issue.message for issue in issues)


def test_wrong_type_is_rejected_by_the_schema() -> None:
    validator = SchemaValidator(load_bundle("1.31.0"))
    manifest = deployment()
    manifest["spec"]["replicas"] = "two"
    issues = validator.check(manifest)
    assert issues


def test_invalid_enum_is_rejected() -> None:
    """The schema bundle carries no enums, so the form layer enforces them."""
    tree = WidgetBuilder(load_bundle("1.31.0")).build("Service", "v1")
    manifest = service()
    manifest["spec"]["type"] = "NotAType"
    issues = check_form(tree, manifest)
    assert "enum" in codes(issues)


def test_valid_deployment_passes_the_schema() -> None:
    validator = SchemaValidator(load_bundle("1.31.0"))
    assert validator.check(deployment()) == []


# -- semantics -------------------------------------------------------------


def test_selector_must_match_the_pod_template() -> None:
    manifest = deployment()
    manifest["spec"]["template"]["metadata"]["labels"] = {"app": "other"}
    issues = analyse([manifest])
    assert "selector-template-mismatch" in codes(issues)


def test_service_selector_must_match_a_workload() -> None:
    issues = analyse([deployment(), service()])
    assert "service-selector-unmatched" not in codes(issues)

    broken = service()
    broken["spec"]["selector"] = {"app": "nope"}
    issues = analyse([deployment(), broken])
    assert "service-selector-unmatched" in codes(issues)


def test_a_service_on_its_own_is_not_a_finding() -> None:
    """The bundle is not the cluster.

    A Service applied on its own may well route to a Deployment that already exists
    in the cluster, so the absence of a workload from the bundle is not a problem.
    """
    assert analyse([service()]) == []


def test_an_ingress_on_its_own_is_not_a_finding() -> None:
    ingress = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {"name": "api"},
        "spec": {
            "rules": [
                {
                    "host": "example.test",
                    "http": {
                        "paths": [
                            {
                                "path": "/",
                                "pathType": "Prefix",
                                "backend": {"service": {"name": "api", "port": {"number": 80}}},
                            }
                        ]
                    },
                }
            ]
        },
    }
    assert analyse([ingress]) == []


def test_an_hpa_on_its_own_is_not_a_finding() -> None:
    hpa = {
        "apiVersion": "autoscaling/v2",
        "kind": "HorizontalPodAutoscaler",
        "metadata": {"name": "api"},
        "spec": {
            "scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": "api"},
            "minReplicas": 1,
            "maxReplicas": 5,
        },
    }
    assert analyse([hpa]) == []


def test_service_target_port_must_match_a_container_port() -> None:
    broken = service()
    broken["spec"]["ports"][0]["targetPort"] = 9999
    issues = analyse([deployment(), broken])
    assert "target-port-unmatched" in codes(issues)


def test_named_target_port_must_match_a_container_port_name() -> None:
    broken = service()
    broken["spec"]["ports"][0]["targetPort"] = "grpc"
    issues = analyse([deployment(), broken])
    assert "target-port-unmatched" in codes(issues)


def test_named_target_port_matches_by_name() -> None:
    ok = service()
    ok["spec"]["ports"][0]["targetPort"] = "http"
    issues = analyse([deployment(), ok])
    assert "target-port-unmatched" not in codes(issues)


def test_dangling_configmap_reference_is_reported() -> None:
    manifest = deployment()
    manifest["spec"]["template"]["spec"]["containers"][0]["envFrom"] = [
        {"configMapRef": {"name": "missing-config"}}
    ]
    issues = analyse([manifest])
    assert "dangling-reference" in codes(issues)


def test_present_configmap_reference_is_not_reported() -> None:
    manifest = deployment()
    manifest["spec"]["template"]["spec"]["containers"][0]["envFrom"] = [
        {"configMapRef": {"name": "app-config"}}
    ]
    config_map = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "app-config"},
        "data": {"KEY": "value"},
    }
    issues = analyse([manifest, config_map])
    assert "dangling-reference" not in codes(issues)


def test_image_without_a_tag_is_flagged() -> None:
    manifest = deployment()
    manifest["spec"]["template"]["spec"]["containers"][0]["image"] = "nginx"
    issues = analyse([manifest])
    assert "image-no-tag" in codes(issues)


def test_limit_without_request_is_flagged() -> None:
    manifest = deployment()
    manifest["spec"]["template"]["spec"]["containers"][0]["resources"] = {"limits": {"cpu": "1"}}
    issues = analyse([manifest])
    assert "limit-without-request" in codes(issues)


def test_mismatched_namespaces_are_reported() -> None:
    manifest = deployment()
    manifest["metadata"]["namespace"] = "prod"
    issues = analyse([manifest, service()])
    assert "namespace-mismatch" in codes(issues)


def test_ingress_backend_must_reference_a_real_service() -> None:
    ingress = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {"name": "api"},
        "spec": {
            "rules": [
                {
                    "host": "example.test",
                    "http": {
                        "paths": [
                            {
                                "path": "/",
                                "pathType": "Prefix",
                                "backend": {"service": {"name": "api", "port": {"number": 80}}},
                            }
                        ]
                    },
                }
            ]
        },
    }
    issues = analyse([deployment(), service(), ingress])
    assert "ingress-backend-missing" not in codes(issues)

    ingress["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]["name"] = "other"
    issues = analyse([deployment(), service(), ingress])
    assert "ingress-backend-missing" in codes(issues)


def test_hpa_target_must_exist() -> None:
    hpa = {
        "apiVersion": "autoscaling/v2",
        "kind": "HorizontalPodAutoscaler",
        "metadata": {"name": "api"},
        "spec": {
            "scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": "nope"},
            "minReplicas": 1,
            "maxReplicas": 5,
        },
    }
    issues = analyse([deployment(), hpa])
    assert "scaler-target-missing" in codes(issues)
