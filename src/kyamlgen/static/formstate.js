/*
 * The pure data-handling logic behind the form.
 *
 * Kept separate from app.js so it can be unit-tested without a browser: every bug
 * found while building this form lived in the path arithmetic, not in the DOM code.
 *
 * Works as a classic browser script (window.KyamlgenFormState) and as a CommonJS
 * module (module.exports) so the same file can be tested under `node --test`.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.KyamlgenFormState = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  /* Read a value at a path of property names and array indices. */
  function getIn(root, parts) {
    var node = root;
    for (var i = 0; i < parts.length; i++) {
      if (node === null || node === undefined || typeof node !== "object") {
        return undefined;
      }
      node = node[parts[i]];
    }
    return node;
  }

  /*
   * Write a value at a path, creating the intermediate containers as needed.
   * An empty string removes the key, because the form treats "" as "not filled in".
   */
  function setIn(root, parts, value) {
    if (!parts.length) return root;
    var node = root;
    for (var i = 0; i < parts.length - 1; i++) {
      var key = parts[i];
      var nextIsIndex = typeof parts[i + 1] === "number";
      if (
        node[key] === null ||
        node[key] === undefined ||
        typeof node[key] !== "object"
      ) {
        node[key] = nextIsIndex ? [] : {};
      }
      node = node[key];
    }
    var last = parts[parts.length - 1];
    if (value === "" || value === null || value === undefined) {
      delete node[last];
    } else {
      node[last] = value;
    }
    return root;
  }

  /*
   * Read a container without creating one.
   *
   * This distinction matters more than it looks. If the renderer created the
   * intermediate objects it walked through, every advanced field it merely displayed
   * would appear in the submitted data as an empty object — and the server would
   * report the missing required fields inside them as real errors.
   */
  function readContainer(root, parts) {
    var node = root;
    for (var i = 0; i < parts.length; i++) {
      if (node === null || node === undefined || typeof node !== "object") {
        return undefined;
      }
      node = node[parts[i]];
    }
    if (node === null || node === undefined || typeof node !== "object") {
      return undefined;
    }
    return node;
  }

  /* Create a container and its ancestors if they do not exist. */
  function ensureContainer(root, parts, wantArray) {
    var node = root;
    for (var i = 0; i < parts.length; i++) {
      var key = parts[i];
      var isLast = i === parts.length - 1;
      var nextIsIndex = !isLast && typeof parts[i + 1] === "number";
      var empty = isLast ? (wantArray ? [] : {}) : nextIsIndex ? [] : {};
      if (
        node[key] === null ||
        node[key] === undefined ||
        typeof node[key] !== "object"
      ) {
        node[key] = empty;
      }
      node = node[key];
    }
    return node;
  }

  /*
   * Delete the value at a path.
   *
   * Used by the per-field and per-section clear buttons.  A numeric last segment
   * means an array element, which is removed with splice — `delete arr[0]` would
   * leave a hole and shift every later item.
   */
  function deleteIn(root, parts) {
    if (!parts.length) return root;
    var node = root;
    for (var i = 0; i < parts.length - 1; i++) {
      if (node === null || node === undefined || typeof node !== "object") {
        return root;
      }
      node = node[parts[i]];
    }
    if (node === null || node === undefined || typeof node !== "object") {
      return root;
    }
    var last = parts[parts.length - 1];
    if (typeof last === "number" && Array.isArray(node)) {
      node.splice(last, 1);
    } else {
      delete node[last];
    }
    return root;
  }

  /* Deep copy through JSON — the data model is plain JSON by construction. */
  function deepCopy(value) {
    return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
  }

  /* Whether two JSON values are equal, for comparing against the preset. */
  function deepEqual(a, b) {
    if (a === b) return true;
    if (a === null || b === null || a === undefined || b === undefined) {
      return false;
    }
    if (typeof a !== "object" || typeof b !== "object") return false;
    return JSON.stringify(a) === JSON.stringify(b);
  }

  return {
    getIn: getIn,
    setIn: setIn,
    deleteIn: deleteIn,
    readContainer: readContainer,
    ensureContainer: ensureContainer,
    deepCopy: deepCopy,
    deepEqual: deepEqual
  };
});
