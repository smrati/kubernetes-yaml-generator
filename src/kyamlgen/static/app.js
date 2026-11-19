(function () {
  "use strict";

  const CFG = window.KYAMLGEN;
  const FormState = window.KyamlgenFormState;

  const state = {
    version: CFG.version,
    objects: [],
    activeId: null,
    mapRows: {},
    kinds: [],
    nextId: 1,
  };

  // -- tiny DOM helpers ---------------------------------------------------

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function pathKey(obj, parts) {
    return obj.id + "|" + parts.join("/");
  }

  // -- data access --------------------------------------------------------

  function getIn(root, parts) {
    return FormState.getIn(root, parts);
  }

  function setIn(root, parts, value) {
    return FormState.setIn(root, parts, value);
  }

  // Reading a container must never create one.  If the renderer created the
  // intermediate objects it walked through, every advanced field it merely displayed
  // would appear in the submitted data as an empty object — and the server would
  // report the missing required fields inside them as real errors.
  function readContainer(obj, parts) {
    return FormState.readContainer(obj.data, parts);
  }

  // Creating a container is explicit, and happens only when the user adds something.
  function ensureContainer(obj, parts, wantArray) {
    return FormState.ensureContainer(obj.data, parts, wantArray);
  }

  function deleteIn(obj, parts) {
    return FormState.deleteIn(obj.data, parts);
  }

  function deepCopy(value) {
    return FormState.deepCopy(value);
  }

  function deepEqual(a, b) {
    return FormState.deepEqual(a, b);
  }

  // A field still holds the preset's value, so it is still a suggestion rather
  // than something the user typed.  Comparing values rather than tracking edits
  // means this needs no state of its own and survives reordering an array.
  function isPresetValue(obj, parts) {
    if (!obj.preset) return false;
    const current = getIn(obj.data, parts);
    if (current === undefined || current === null || current === "") return false;
    return deepEqual(current, getIn(obj.preset, parts));
  }

  function presetDot(obj, parts) {
    if (!isPresetValue(obj, parts)) return null;
    const dot = el("span", "preset-dot", "•");
    dot.title = "Still the template's value — click the × to clear it";
    return dot;
  }

  function activeObject() {
    return (
      state.objects.find(function (o) {
        return o.id === state.activeId;
      }) || state.objects[0]
    );
  }

  // -- rendering ----------------------------------------------------------

  function renderNode(node, parts, depth) {
    switch (node.kind) {
      case "object":
        return renderObject(node, parts, depth);
      case "array":
        return renderArray(node, parts, depth);
      case "map":
        return renderMap(node, parts, depth);
      default:
        return renderScalar(node, parts);
    }
  }

  function renderObject(node, parts, depth) {
    const obj = activeObject();
    const details = el("details", "fieldset");
    if (depth <= 1) details.open = true;

    const summary = el("summary");
    summary.appendChild(document.createTextNode(node.label || node.name));
    if (node.required) summary.appendChild(el("span", "req", "required"));
    summary.appendChild(el("span", "spacer"));
    summary.appendChild(clearSectionButton(obj, parts, "Clear"));
    details.appendChild(summary);

    const body = el("div", "fieldset-body");
    const children = node.children || [];
    children
      .filter(function (child) {
        return !child.advanced;
      })
      .forEach(function (child) {
        body.appendChild(renderNode(child, parts.concat(child.name), depth + 1));
      });

    const advanced = children.filter(function (child) {
      return child.advanced;
    });
    if (advanced.length) {
      const adv = el("details", "fieldset");
      const advSummary = el("summary");
      advSummary.appendChild(document.createTextNode("Advanced"));
      adv.appendChild(advSummary);
      const advBody = el("div", "fieldset-body");
      advanced.forEach(function (child) {
        advBody.appendChild(
          renderNode(child, parts.concat(child.name), depth + 1)
        );
      });
      adv.appendChild(advBody);
      body.appendChild(adv);
    }

    details.appendChild(body);
    return details;
  }

  function renderArray(node, parts, depth) {
    const obj = activeObject();
    const details = el("details", "fieldset");
    if (depth <= 1) details.open = true;

    const summary = el("summary");
    summary.appendChild(document.createTextNode(node.label || node.name));
    if (node.required) summary.appendChild(el("span", "req", "required"));
    details.appendChild(summary);

    const body = el("div", "fieldset-body");
    const existing = readContainer(obj, parts);
    const list = Array.isArray(existing) ? existing : [];
    const template = node.item || { kind: "json" };
    const count = Math.max(list.length, template.kind === "object" ? 1 : 0);

    const wrap = el("div", "array-items");
    for (let index = 0; index < count; index++) {
      const item = el("div", "array-item");
      const head = el("div", "array-item-head");
      head.appendChild(el("span", null, node.itemLabel || "item " + (index + 1)));
      head.appendChild(el("span", "spacer"));
      if (index < list.length) {
        const remove = el("button", "btn-tiny", "Remove");
        remove.type = "button";
        remove.addEventListener("click", function () {
          const current = readContainer(activeObject(), parts);
          if (Array.isArray(current)) {
            current.splice(index, 1);
          }
          refresh();
        });
        head.appendChild(remove);
      }
      item.appendChild(head);
      item.appendChild(renderNode(template, parts.concat(index), depth + 1));
      wrap.appendChild(item);
    }
    body.appendChild(wrap);

    const add = el(
      "button",
      "btn-tiny",
      "+ Add " + (node.itemLabel || "item").toLowerCase()
    );
    add.type = "button";
    add.addEventListener("click", function () {
      ensureContainer(activeObject(), parts, true).push({});
      refresh();
    });
    body.appendChild(add);

    details.appendChild(body);
    return details;
  }

  function rowsFor(obj, parts) {
    const key = pathKey(obj, parts);
    if (!state.mapRows[key]) {
      const existing = getIn(obj.data, parts) || {};
      state.mapRows[key] = Object.keys(existing).map(function (mapKey) {
        return { key: mapKey, value: existing[mapKey] };
      });
    }
    return state.mapRows[key];
  }

  function syncMap(obj, parts, rows) {
    const target = ensureContainer(obj, parts, false);
    Object.keys(target).forEach(function (mapKey) {
      delete target[mapKey];
    });
    rows.forEach(function (row) {
      if (row.key !== "" && row.value !== "") {
        target[row.key] = row.value;
      }
    });
  }

  function renderMap(node, parts, depth) {
    const obj = activeObject();
    const details = el("details", "fieldset");
    if (depth <= 1) details.open = true;

    const summary = el("summary");
    summary.appendChild(document.createTextNode(node.label || node.name));
    if (node.required) summary.appendChild(el("span", "req", "required"));
    const dot = presetDot(obj, parts);
    if (dot) summary.appendChild(dot);
    details.appendChild(summary);

    const body = el("div", "fieldset-body");
    const rows = rowsFor(obj, parts);

    const wrap = el("div", "map-rows");
    rows.forEach(function (row, index) {
      const line = el("div", "map-row");
      const keyInput = el("input", "input");
      keyInput.type = "text";
      keyInput.placeholder = node.keyPlaceholder || "key";
      keyInput.value = row.key;

      const valueInput = el("input", "input");
      valueInput.type = "text";
      valueInput.placeholder = node.valuePlaceholder || "value";
      valueInput.value = row.value;

      const remove = el("button", "btn-tiny", "x");
      remove.type = "button";
      remove.addEventListener("click", function () {
        rows.splice(index, 1);
        syncMap(activeObject(), parts, rows);
        refresh();
      });

      keyInput.addEventListener("input", function () {
        row.key = keyInput.value;
        syncMap(activeObject(), parts, rows);
        scheduleGenerate();
      });
      valueInput.addEventListener("input", function () {
        row.value = valueInput.value;
        syncMap(activeObject(), parts, rows);
        scheduleGenerate();
      });

      line.appendChild(keyInput);
      line.appendChild(valueInput);
      line.appendChild(remove);
      wrap.appendChild(line);
    });
    body.appendChild(wrap);

    const add = el("button", "btn-tiny", "+ Add entry");
    add.type = "button";
    add.addEventListener("click", function () {
      rows.push({ key: "", value: "" });
      refresh();
    });
    body.appendChild(add);

    details.appendChild(body);
    return details;
  }

  function renderScalar(node, parts) {
    const obj = activeObject();
    const wrap = el("div", "field");

    const label = el("label");
    label.appendChild(document.createTextNode(node.label || node.name));
    if (node.required) label.appendChild(el("span", "req", "*"));
    const dot = presetDot(obj, parts);
    if (dot) label.appendChild(dot);
    wrap.appendChild(label);

    const current = getIn(obj.data, parts);
    let input;
    let holder = null; // where the input lives, when it needs a wrapper of its own

    if (node.kind === "boolean") {
      const row = el("div", "checkbox-row");
      input = el("input");
      input.type = "checkbox";
      input.checked = current === true;
      row.appendChild(input);
      row.appendChild(el("span", "muted", current === true ? "enabled" : "disabled"));
      holder = row;
      input.addEventListener("change", function () {
        setIn(activeObject().data, parts, input.checked);
        scheduleGenerate();
      });
    } else if (node.kind === "select") {
      input = el("select", "select");
      const blank = el("option", null, "—");
      blank.value = "";
      input.appendChild(blank);
      (node.enum || []).forEach(function (option) {
        const node2 = el("option", null, String(option));
        node2.value = String(option);
        input.appendChild(node2);
      });
      input.value = current === undefined ? "" : String(current);
      input.addEventListener("change", function () {
        setIn(activeObject().data, parts, input.value);
        scheduleGenerate();
      });
    } else if (node.kind === "json" || node.kind === "text") {
      input = el("textarea", "textarea");
      input.value = current === undefined ? "" : String(current);
      if (node.placeholder) input.placeholder = node.placeholder;
      input.addEventListener("input", function () {
        setIn(activeObject().data, parts, input.value);
        scheduleGenerate();
      });
    } else {
      input = el("input", "input");
      input.type = node.kind === "integer" || node.kind === "number" ? "number" : "text";
      if (node.min !== undefined) input.min = node.min;
      if (node.max !== undefined) input.max = node.max;
      if (node.placeholder) input.placeholder = node.placeholder;
      if (node.kind === "quantity" || node.kind === "int-or-string") {
        input.type = "text";
      }
      input.value = current === undefined ? "" : String(current);
      input.addEventListener("input", function () {
        let value = input.value;
        if (node.kind === "integer" || node.kind === "number") {
          value = value === "" ? "" : Number(value);
        }
        setIn(activeObject().data, parts, value);
        scheduleGenerate();
      });
    }

    if (current !== undefined && current !== null && current !== "") {
      const row = el("div", "field-row");
      row.appendChild(holder || input);
      row.appendChild(clearFieldButton(obj, parts, input));
      wrap.appendChild(row);
    } else {
      wrap.appendChild(holder || input);
    }

    if (node.description) {
      const hint = el("div", "hint");
      hint.textContent = truncate(node.description);
      wrap.appendChild(hint);
    }
    return wrap;
  }

  // A one-click clear for a single value.
  function clearFieldButton(obj, parts, input) {
    const button = el("button", "clear-btn", "×");
    button.type = "button";
    button.title = "Clear this value";
    button.addEventListener("click", function () {
      deleteIn(activeObject(), parts);
      if (input.type === "checkbox") input.checked = false;
      else input.value = "";
      refresh();
    });
    return button;
  }

  // A one-click clear for a whole section.
  function clearSectionButton(obj, parts, label) {
    const button = el("button", "clear-section", label);
    button.type = "button";
    button.title = "Clear everything in this section";
    button.addEventListener("click", function (event) {
      // Clicking inside a <summary> toggles the section; this must not.
      event.preventDefault();
      event.stopPropagation();
      deleteIn(activeObject(), parts);
      refresh();
    });
    return button;
  }

  function truncate(text) {
    if (text.length <= 320) return text;
    return text.slice(0, 320).replace(/\s+\S*$/, "") + "…";
  }

  // -- object tabs --------------------------------------------------------

  function renderObjects() {
    const host = document.getElementById("objects");
    host.innerHTML = "";
    state.objects.forEach(function (obj) {
      const tab = el("div", "object-tab" + (obj.id === state.activeId ? " active" : ""));
      tab.appendChild(el("span", null, obj.kind));
      const remove = el("button", "remove", "×");
      remove.title = "Remove object";
      remove.addEventListener("click", function (event) {
        event.stopPropagation();
        state.objects = state.objects.filter(function (item) {
          return item.id !== obj.id;
        });
        if (state.activeId === obj.id) {
          state.activeId = state.objects.length ? state.objects[0].id : null;
        }
        refresh();
      });
      tab.appendChild(remove);
      tab.addEventListener("click", function () {
        state.activeId = obj.id;
        refresh();
      });
      host.appendChild(tab);
    });
  }

  function renderForm() {
    const host = document.getElementById("form");
    host.innerHTML = "";
    const obj = activeObject();
    if (!obj) return;
    const root = obj.tree.children || [];
    root.forEach(function (child) {
      host.appendChild(renderNode(child, [child.name], 0));
    });
  }

  function refresh() {
    renderObjects();
    renderForm();
    renderToolbar();
    scheduleGenerate();
  }

  // -- generation ---------------------------------------------------------

  let timer = null;

  function scheduleGenerate() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(generate, 220);
  }

  function generate() {
    const payload = {
      version: state.version,
      objects: state.objects.map(function (obj) {
        return {
          apiVersion: obj.apiVersion,
          kind: obj.kind,
          manifest: obj.data,
        };
      }),
    };

    fetch("/api/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (result) {
        document.getElementById("yaml").textContent = result.yaml || "";
        renderIssues(result.issues || []);
      })
      .catch(function (error) {
        document.getElementById("yaml").textContent = String(error);
      });
  }

  function renderIssues(issues) {
    const host = document.getElementById("issues");
    host.innerHTML = "";
    if (!issues.length) {
      const ok = el("div", "issue issue-ok");
      ok.appendChild(el("span", "level", "ok"));
      ok.appendChild(el("span", null, "No problems found."));
      host.appendChild(ok);
      return;
    }
    issues.forEach(function (issue) {
      const row = el(
        "div",
        "issue " + (issue.level === "error" ? "issue-error" : "issue-warning")
      );
      row.appendChild(el("span", "level", issue.level));
      const text = el("span");
      if (issue.objectIndex !== null && issue.objectIndex !== undefined) {
        const owner = state.objects[issue.objectIndex];
        if (owner) {
          text.appendChild(el("strong", null, owner.kind + ": "));
        }
      }
      text.appendChild(document.createTextNode(issue.message));
      row.appendChild(text);
      host.appendChild(row);
    });
  }

  // -- boot ---------------------------------------------------------------

  function addObject(apiVersion, kind, tree, preset) {
    const obj = {
      id: state.nextId++,
      apiVersion: apiVersion,
      kind: kind,
      tree: tree,
      preset: preset || null,
      data: { apiVersion: apiVersion, kind: kind },
    };
    if (obj.preset) {
      obj.data = deepCopy(obj.preset);
    }
    state.objects.push(obj);
    state.activeId = obj.id;
    refresh();
  }

  // Wipe one object back to nothing.  The cached map rows have to go too, or the
  // rows reappear on the next render and put the values straight back.
  function clearObject(obj) {
    obj.data = { apiVersion: obj.apiVersion, kind: obj.kind };
    forgetMapRows(obj);
    refresh();
  }

  function resetObject(obj) {
    if (!obj.preset) return;
    obj.data = deepCopy(obj.preset);
    forgetMapRows(obj);
    refresh();
  }

  function forgetMapRows(obj) {
    const prefix = obj.id + "|";
    Object.keys(state.mapRows).forEach(function (key) {
      if (key.indexOf(prefix) === 0) delete state.mapRows[key];
    });
  }

  function renderToolbar() {
    const obj = activeObject();
    const reset = document.getElementById("reset-template");
    const clear = document.getElementById("clear-values");
    if (reset) reset.hidden = !(obj && obj.preset);
    if (clear) clear.hidden = !obj;
  }

  function populateKindPicker() {
    const select = document.getElementById("add-kind");
    const groups = {};
    state.kinds.forEach(function (kind) {
      (groups[kind.category] = groups[kind.category] || []).push(kind);
    });
    Object.keys(groups)
      .sort()
      .forEach(function (category) {
        const group = el("optgroup");
        group.label = category;
        groups[category].forEach(function (kind) {
          const option = el("option", null, kind.kind + "  (" + kind.apiVersion + ")");
          option.value = kind.apiVersion + "|" + kind.kind;
          group.appendChild(option);
        });
        select.appendChild(group);
      });
  }

  document.getElementById("add-object").addEventListener("click", function () {
    const value = document.getElementById("add-kind").value;
    if (!value) return;
    const parts = value.split("|");
    fetch(
      "/api/tree?apiVersion=" +
        encodeURIComponent(parts[0]) +
        "&kind=" +
        encodeURIComponent(parts[1]) +
        "&version=" +
        encodeURIComponent(state.version)
    )
      .then(function (response) {
        return response.json();
      })
      .then(function (result) {
        addObject(parts[0], parts[1], result.tree, result.preset);
      });
  });

  document.getElementById("reset-template").addEventListener("click", function () {
    const obj = activeObject();
    if (obj) resetObject(obj);
  });

  document.getElementById("clear-values").addEventListener("click", function () {
    const obj = activeObject();
    if (obj) clearObject(obj);
  });

  document.getElementById("copy").addEventListener("click", function () {
    const text = document.getElementById("yaml").textContent;
    const button = document.getElementById("copy");
    navigator.clipboard.writeText(text).then(function () {
      button.textContent = "Copied";
      button.classList.add("copy-flash");
      setTimeout(function () {
        button.textContent = "Copy";
        button.classList.remove("copy-flash");
      }, 1200);
    });
  });

  document.getElementById("download").addEventListener("click", function () {
    const text = document.getElementById("yaml").textContent;
    const blob = new Blob([text], { type: "text/yaml" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "manifest.yaml";
    link.click();
    URL.revokeObjectURL(link.href);
  });

  fetch("/api/kinds?version=" + encodeURIComponent(state.version))
    .then(function (response) {
      return response.json();
    })
    .then(function (result) {
      state.kinds = result.kinds;
      populateKindPicker();
    });

  addObject(CFG.apiVersion, CFG.kind, CFG.tree, CFG.preset);
})();
