"use strict";

/*
 * Tests for the form's data-handling logic.
 *
 * Run with:  node --test tests/js/
 *
 * These exist because every bug found while building the form lived in this path
 * arithmetic rather than in the DOM code — including the one where the renderer
 * created empty objects for advanced fields it only meant to display, which made the
 * server report phantom "required" errors.
 */

const test = require("node:test");
const assert = require("node:assert");
const path = require("node:path");

const FormState = require(
  path.join(__dirname, "..", "..", "src", "kyamlgen", "static", "formstate.js")
);

test("getIn reads a nested value", () => {
  const data = { spec: { template: { spec: { containers: [{ image: "nginx" }] } } } };
  assert.strictEqual(
    FormState.getIn(data, ["spec", "template", "spec", "containers", 0, "image"]),
    "nginx"
  );
  assert.strictEqual(
    FormState.getIn(data, ["spec", "template", "spec", "containers", 1, "image"]),
    undefined
  );
  assert.strictEqual(FormState.getIn(data, ["nope"]), undefined);
});

test("setIn creates the intermediate containers it needs", () => {
  const data = {};
  FormState.setIn(data, ["spec", "template", "spec", "containers", 0, "image"], "nginx");
  assert.deepStrictEqual(data, {
    spec: { template: { spec: { containers: [{ image: "nginx" }] } } },
  });
});

test("setIn creates an array where the path says there is one", () => {
  const data = {};
  FormState.setIn(data, ["spec", "ports", 0, "port"], 80);
  assert.deepStrictEqual(data, { spec: { ports: [{ port: 80 }] } });
});

test("setIn removes the key when the value is emptied", () => {
  const data = { metadata: { name: "api", namespace: "prod" } };
  FormState.setIn(data, ["metadata", "name"], "");
  assert.deepStrictEqual(data, { metadata: { namespace: "prod" } });
});

test("setIn keeps zero and false", () => {
  const data = {};
  FormState.setIn(data, ["spec", "replicas"], 0);
  FormState.setIn(data, ["spec", "paused"], false);
  assert.deepStrictEqual(data, { spec: { replicas: 0, paused: false } });
});

test("readContainer never creates anything", () => {
  const data = {};
  const parts = ["spec", "template", "spec", "affinity", "nodeAffinity"];
  assert.strictEqual(FormState.readContainer(data, parts), undefined);
  assert.deepStrictEqual(data, {});
});

test("readContainer returns an existing container", () => {
  const data = { spec: { ports: [{ port: 80 }] } };
  assert.deepStrictEqual(FormState.readContainer(data, ["spec", "ports"]), [
    { port: 80 }
  ]);
  assert.deepStrictEqual(data, { spec: { ports: [{ port: 80 }] } });
});

test("ensureContainer creates the whole path", () => {
  const data = {};
  FormState.ensureContainer(data, ["spec", "ports"], true);
  assert.deepStrictEqual(data, { spec: { ports: [] } });
});

test("ensureContainer creates a map, not an array", () => {
  const data = {};
  FormState.ensureContainer(data, ["metadata", "labels"], false);
  assert.deepStrictEqual(data, { metadata: { labels: {} } });
});

test("ensureContainer creates an array for an indexed path", () => {
  const data = {};
  FormState.ensureContainer(data, ["spec", "containers", 0, "ports"], true);
  assert.deepStrictEqual(data, { spec: { containers: [{ ports: [] }] } });
});

test("reading a path never disturbs the data", () => {
  const data = { apiVersion: "apps/v1", kind: "Deployment" };
  const before = JSON.stringify(data);
  FormState.readContainer(data, ["spec", "template", "spec", "containers"]);
  FormState.getIn(data, ["spec", "template", "spec", "containers", 0, "image"]);
  assert.strictEqual(JSON.stringify(data), before);
});

test("writing into a nested array item keeps the siblings", () => {
  const data = {
    spec: {
      template: {
        spec: {
          containers: [{ name: "web", ports: [{ containerPort: 8080 }] }],
        },
      },
    },
  };
  FormState.setIn(
    data,
    ["spec", "template", "spec", "containers", 0, "ports", 0, "name"],
    "http"
  );
  assert.deepStrictEqual(data.spec.template.spec.containers[0].ports[0], {
    containerPort: 8080,
    name: "http",
  });
});

test("deleteIn removes a single value", () => {
  const data = { metadata: { name: "api", namespace: "prod" } };
  FormState.deleteIn(data, ["metadata", "name"]);
  assert.deepStrictEqual(data, { metadata: { namespace: "prod" } });
});

test("deleteIn removes a whole subtree", () => {
  const data = { spec: { template: { spec: { containers: [{ name: "web" }] } } } };
  FormState.deleteIn(data, ["spec", "template"]);
  assert.deepStrictEqual(data, { spec: {} });
});

test("deleteIn on a missing path changes nothing", () => {
  const data = { metadata: { name: "api" } };
  FormState.deleteIn(data, ["spec", "template", "spec"]);
  assert.deepStrictEqual(data, { metadata: { name: "api" } });
});

test("deleteIn on an array index splices rather than leaving a hole", () => {
  const data = { containers: [{ name: "a" }, { name: "b" }] };
  FormState.deleteIn(data, ["containers", 0]);
  assert.deepStrictEqual(data, { containers: [{ name: "b" }] });
});

test("deleteIn removes a field inside an array item", () => {
  const data = { containers: [{ name: "a", image: "nginx" }] };
  FormState.deleteIn(data, ["containers", 0, "image"]);
  assert.deepStrictEqual(data, { containers: [{ name: "a" }] });
});

test("deepCopy leaves the original alone", () => {
  const original = { metadata: { labels: { app: "api" } } };
  const copy = FormState.deepCopy(original);
  copy.metadata.labels.app = "changed";
  assert.strictEqual(original.metadata.labels.app, "api");
});

test("deepEqual compares by value", () => {
  assert.strictEqual(FormState.deepEqual({ a: [1, 2] }, { a: [1, 2] }), true);
  assert.strictEqual(FormState.deepEqual({ a: [1, 2] }, { a: [1, 3] }), false);
  assert.strictEqual(FormState.deepEqual(undefined, undefined), true);
  assert.strictEqual(FormState.deepEqual("on", "on"), true);
  assert.strictEqual(FormState.deepEqual(null, undefined), false);
});
