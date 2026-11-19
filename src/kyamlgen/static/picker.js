(function () {
  "use strict";

  const search = document.getElementById("kind-search");
  const container = document.getElementById("kind-groups");
  const kinds = window.KINDS || [];

  function render(filter) {
    const needle = (filter || "").trim().toLowerCase();
    const matches = kinds.filter(function (kind) {
      if (!needle) return true;
      return (
        kind.kind.toLowerCase().indexOf(needle) !== -1 ||
        kind.apiVersion.toLowerCase().indexOf(needle) !== -1 ||
        kind.category.toLowerCase().indexOf(needle) !== -1 ||
        kind.plural.toLowerCase().indexOf(needle) !== -1
      );
    });

    container.innerHTML = "";
    const groups = {};
    matches.forEach(function (kind) {
      (groups[kind.category] = groups[kind.category] || []).push(kind);
    });

    const names = Object.keys(groups).sort();
    if (!names.length) {
      container.innerHTML = '<p class="muted">No kind matches that search.</p>';
      return;
    }

    names.forEach(function (name) {
      const section = document.createElement("div");
      section.className = "group";

      const heading = document.createElement("h2");
      heading.textContent = name;
      section.appendChild(heading);

      const grid = document.createElement("div");
      grid.className = "kind-grid";

      groups[name].forEach(function (kind) {
        const link = document.createElement("a");
        link.className = "kind-card" + (kind.authorable ? "" : " dimmed");
        link.href =
          "/form?apiVersion=" +
          encodeURIComponent(kind.apiVersion) +
          "&kind=" +
          encodeURIComponent(kind.kind);

        const title = document.createElement("span");
        title.className = "kind-name";
        title.textContent = kind.kind;

        const api = document.createElement("span");
        api.className = "kind-api";
        api.textContent = kind.apiVersion + (kind.namespaced ? "" : " · cluster");

        link.appendChild(title);
        link.appendChild(api);
        grid.appendChild(link);
      });

      section.appendChild(grid);
      container.appendChild(section);
    });
  }

  search.addEventListener("input", function () {
    render(search.value);
  });

  render("");
})();
