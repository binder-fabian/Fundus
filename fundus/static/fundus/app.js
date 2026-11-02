// Fundus – registriert den Service Worker (installierbare App).
if ("serviceWorker" in navigator && window.isSecureContext) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

// Lange Häkchen-Listen (z. B. Teammitglieder) bekommen ein Suchfeld.
// Angehakte Einträge bleiben immer sichtbar.
document.addEventListener("DOMContentLoaded", () => {
  const groups = new Map();
  for (const input of document.querySelectorAll("input[type=checkbox][data-filter]")) {
    const list = input.closest(".field")?.querySelector("div[id]");
    if (list && !groups.has(list)) groups.set(list, input.dataset.filter);
  }
  for (const [list, placeholder] of groups) {
    const rows = [...list.children];
    if (rows.length < 8) continue;
    const search = document.createElement("input");
    search.type = "search";
    search.placeholder = placeholder;
    search.className = "checklist-filter";
    search.setAttribute("aria-label", placeholder);
    search.addEventListener("input", () => {
      const q = search.value.trim().toLocaleLowerCase("de");
      for (const row of rows) {
        const checked = row.querySelector("input")?.checked;
        const match = row.textContent.toLocaleLowerCase("de").includes(q);
        row.hidden = !(checked || match);
      }
    });
    search.addEventListener("keydown", (e) => {
      if (e.key === "Enter") e.preventDefault();
    });
    list.before(search);
  }
});
