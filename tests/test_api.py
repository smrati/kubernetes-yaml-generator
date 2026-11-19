from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kyamlgen.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_index_lists_kinds(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Deployment" in response.text


def test_kinds_endpoint_returns_the_catalogue(client: TestClient) -> None:
    response = client.get("/api/kinds?version=1.31.0")
    assert response.status_code == 200
    payload = response.json()
    kinds = payload["kinds"]
    assert payload["version"] == "1.31.0"
    names = {kind["kind"] for kind in kinds}
    assert {"Deployment", "Service", "Ingress", "Node", "CronJob"} <= names
    node = next(kind for kind in kinds if kind["kind"] == "Node")
    assert node["namespaced"] is False
    assert node["authorable"] is False
    assert node["note"]


def test_form_page_embeds_the_widget_tree(client: TestClient) -> None:
    response = client.get("/form?apiVersion=apps/v1&kind=Deployment")
    assert response.status_code == 200
    assert "KYAMLGEN" in response.text
    assert "Deployment" in response.text
    assert "formstate.js" in response.text


def test_tree_endpoint(client: TestClient) -> None:
    response = client.get("/api/tree?apiVersion=apps/v1&kind=Deployment")
    assert response.status_code == 200
    tree = response.json()
    assert tree["kind"] == "object"
    assert [child["name"] for child in tree["children"]] == ["metadata", "spec"]


def test_render_produces_yaml_and_reports_issues(client: TestClient) -> None:
    payload = {
        "version": "1.31.0",
        "objects": [
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "manifest": {
                    "metadata": {"name": "api", "labels": {"app": "api"}},
                    "spec": {
                        "replicas": 2,
                        "selector": {"matchLabels": {"app": "api"}},
                        "template": {
                            "metadata": {"labels": {"app": "api"}},
                            "spec": {"containers": [{"name": "web", "image": "nginx:1.27"}]},
                        },
                    },
                },
            }
        ],
    }
    response = client.post("/api/render", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["ok"] is True
    assert "kind: Deployment" in result["yaml"]
    assert "image: nginx:1.27" in result["yaml"]


def test_render_reports_a_selector_mismatch(client: TestClient) -> None:
    payload = {
        "version": "1.31.0",
        "objects": [
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "manifest": {
                    "metadata": {"name": "api"},
                    "spec": {
                        "selector": {"matchLabels": {"app": "api"}},
                        "template": {
                            "metadata": {"labels": {"app": "other"}},
                            "spec": {"containers": [{"name": "web", "image": "nginx"}]},
                        },
                    },
                },
            }
        ],
    }
    result = client.post("/api/render", json=payload).json()
    assert result["ok"] is False
    assert any(issue["code"] == "selector-template-mismatch" for issue in result["issues"])


def test_render_checks_objects_against_each_other(client: TestClient) -> None:
    payload = {
        "version": "1.31.0",
        "objects": [
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "manifest": {
                    "metadata": {"name": "api", "labels": {"app": "api"}},
                    "spec": {
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
                },
            },
            {
                "apiVersion": "v1",
                "kind": "Service",
                "manifest": {
                    "metadata": {"name": "api"},
                    "spec": {
                        "selector": {"app": "api"},
                        "ports": [{"port": 80, "targetPort": 8080}],
                    },
                },
            },
        ],
    }
    result = client.post("/api/render", json=payload).json()
    assert result["ok"] is True
    assert result["yaml"].count("---") == 2


def test_validate_endpoint_accepts_pasted_yaml(client: TestClient) -> None:
    text = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  labels:
    app: api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: web
          image: nginx:1.27
"""
    result = client.post("/api/validate", json={"version": "1.31.0", "yaml": text}).json()
    assert result["ok"] is True
    assert "kind: Deployment" in result["yaml"]


def test_validate_endpoint_reports_a_bad_field(client: TestClient) -> None:
    text = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  nonsense: true
"""
    result = client.post("/api/validate", json={"version": "1.31.0", "yaml": text}).json()
    assert result["ok"] is False
    assert any("nonsense" in issue["message"] for issue in result["issues"])


def test_healthz(client: TestClient) -> None:
    assert client.get("/healthz").text == "ok"
