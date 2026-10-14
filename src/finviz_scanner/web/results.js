/* Session-only stock selection. All exports originate from verified current results. */
(() => {
  const byId = id => document.getElementById(id);
  const states = new Map();
  const requests = new Set();
  let activeId = "";
  let configurationKey = "";
  let generation = 0;
  let configuredScreens = [];
  const dateText = value => value ? new Date(value).toLocaleString() : "unavailable";
  const state = () => states.get(activeId);
  const initialState = () => ({data: null, pending: null, latest: null, selected: new Set(), tab: "current", query: "", sort: "finviz_rank", ascending: true, error: ""});

  function changeFor(item, currentState) {
    if (currentState.tab === "removals") return "Removed";
    if (currentState.data.baseline) return "Baseline";
    return currentState.data.additions.some(row => row.ticker === item.ticker) ? "New" : "Unchanged";
  }

  function visibleRows(currentState) {
    if (!currentState?.data) return [];
    const query = currentState.query.trim().toLowerCase();
    const rows = currentState.data[currentState.tab].filter(item =>
      `${item.ticker} ${item.company_name || ""}`.toLowerCase().includes(query));
    return rows.sort((a, b) => {
      const av = currentState.sort === "change" ? changeFor(a, currentState) : a[currentState.sort];
      const bv = currentState.sort === "change" ? changeFor(b, currentState) : b[currentState.sort];
      const order = currentState.sort === "finviz_rank" ? av - bv : String(av || "").localeCompare(String(bv || ""));
      return (currentState.ascending ? order : -order) || a.ticker.localeCompare(b.ticker);
    });
  }

  function exportText(currentState) {
    if (!currentState?.data || currentState.error) return "";
    return currentState.data.current.filter(item => currentState.selected.has(item.ticker))
      .sort((a, b) => a.finviz_rank - b.finviz_rank || a.ticker.localeCompare(b.ticker))
      .map(item => item.tv_symbol).join(",");
  }

  function renderMeta() {
    const s = state();
    const run = s?.data?.successful_run;
    byId("results-success").textContent = run ? `Successful result · ${dateText(run.finished_at)}${s.data.baseline ? " · Baseline" : ""}` : "No successful results yet. Run a visible scan to begin.";
    byId("results-attempt").textContent = s?.latest ? `Latest attempt · ${s.latest.status} · ${dateText(s.latest.started_at)}` : "Latest attempt: unavailable";
    byId("update-results").hidden = !s?.pending;
    byId("results-error").hidden = !s?.error;
    byId("results-error").textContent = s?.error || "";
  }

  function renderExport() {
    const s = state();
    const text = exportText(s);
    const count = s?.selected.size || 0;
    byId("watchlist-preview").value = text;
    byId("selection-total").textContent = `${count} symbols`;
    byId("results-count").textContent = `${visibleRows(s).length} visible · ${count} selected`;
    byId("copy-selected").disabled = !text;
    byId("download-selected").disabled = !text;
    byId("clear-selection").disabled = !count;
    byId("select-visible").disabled = !s?.data || !!s.error || s.tab === "removals" || !visibleRows(s).length;
  }

  function renderTable() {
    const s = state();
    const body = byId("results-body");
    body.replaceChildren();
    const rows = visibleRows(s);
    if (!rows.length) {
      const row = document.createElement("tr"), cell = document.createElement("td");
      cell.colSpan = 6; cell.className = "empty";
      cell.textContent = s?.error ? "Results unavailable." : !s?.data ? "No successful results yet." : s.data.baseline && s.tab !== "current" ? "Baseline run: no changes to compare yet." : "No matching stocks.";
      row.append(cell); body.append(row);
    }
    for (const item of rows) {
      const row = document.createElement("tr"), selectCell = document.createElement("td");
      if (s.tab !== "removals") {
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox"; checkbox.checked = s.selected.has(item.ticker);
        checkbox.disabled = !!s.error;
        checkbox.setAttribute("aria-label", `Select ${item.ticker}`);
        checkbox.addEventListener("change", () => {
          if (checkbox.checked) s.selected.add(item.ticker); else s.selected.delete(item.ticker);
          byId("export-feedback").textContent = "";
          renderExport();
        });
        selectCell.append(checkbox);
      } else selectCell.textContent = "—";
      row.append(selectCell);
      for (const value of [item.ticker, item.company_name || "—", item.exchange, item.finviz_rank, changeFor(item, s)]) {
        const cell = document.createElement("td"); cell.textContent = value; row.append(cell);
      }
      body.append(row);
    }
    document.querySelectorAll("[data-result-tab]").forEach(button => {
      const tab = button.dataset.resultTab;
      const labels = {current: "Current", additions: "New additions", unchanged: "Unchanged", removals: "Removed"};
      button.textContent = `${labels[tab]} (${s?.data?.[tab].length || 0})`;
      button.setAttribute("aria-pressed", String(s?.tab === tab));
    });
    document.querySelectorAll("[data-result-sort]").forEach(button => {
      button.parentElement.setAttribute("aria-sort", button.dataset.resultSort === s?.sort ? s.ascending ? "ascending" : "descending" : "none");
    });
    renderExport();
  }

  function adopt(s, data) {
    s.data = data.successful_run ? data : null;
    s.latest = data.latest_attempt;
    s.pending = null;
    s.selected = new Set(data.current.map(item => item.ticker));
  }

  async function refreshResults() {
    const id = activeId, version = generation;
    const requestKey = `${version}:${id}`;
    if (!id || requests.has(requestKey)) return;
    requests.add(requestKey);
    try {
      const response = await fetch(`/api/results?screen_id=${encodeURIComponent(id)}`, {cache: "no-store"});
      const data = await response.json();
      if (version !== generation) return;
      const s = states.get(id);
      if (!response.ok) throw new Error(data.error || "Results unavailable.");
      const recovered = !!s.error;
      s.error = "";
      s.latest = data.latest_attempt;
      if (!s.data) {
        adopt(s, data);
        if (id === activeId) renderTable();
      } else if (data.successful_run?.run_id !== s.data.successful_run.run_id) {
        s.pending = data;
      } else if (recovered && id === activeId) renderTable();
      if (id === activeId) { renderMeta(); renderExport(); }
    } catch (error) {
      if (version !== generation) return;
      const s = states.get(id);
      if (s) {
        s.error = error.message || "Results disconnected. Retry when the dashboard reconnects.";
        if (id === activeId) { renderMeta(); renderTable(); }
      }
    } finally { requests.delete(requestKey); }
  }

  function renderPreset() {
    const screen = configuredScreens.find(item => item.id === activeId);
    const summary = screen?.preset_summary;
    byId("preset-title").textContent = screen ? `${screen.name} · preset settings` : "Selected preset";
    byId("preset-count").textContent = summary ? `${summary.filters.length} filter${summary.filters.length === 1 ? "" : "s"}` : "";
    byId("preset-context").textContent = summary ? `View: ${summary.view} · Sort: ${summary.sort}${screen.enabled ? "" : " · Disabled for scans"}` : "Select a configured screen to see its settings.";
    const options = byId("preset-options"); options.replaceChildren();
    for (const filter of summary?.filters || []) {
      const item = document.createElement("div");
      const label = document.createElement("dt"), value = document.createElement("dd");
      label.textContent = filter.label; value.textContent = filter.value;
      if (!filter.recognized) item.className = "unrecognized";
      item.append(label, value); options.append(item);
    }
    byId("preset-note").textContent = !summary ? "Settings unavailable." : !summary.filters.length ? "No filters are configured. These settings apply to the next scan." : "All filters apply together. Configured settings for the next scan; saved results may reflect earlier settings.";
  }

  function activate(id) {
    activeId = id;
    if (id && !states.has(id)) states.set(id, initialState());
    byId("results-search").value = state()?.query || "";
    byId("export-feedback").textContent = "";
    renderPreset(); renderMeta(); renderTable();
    refreshResults();
  }

  function configure(configuration) {
    const key = JSON.stringify([configuration.ready, configuration.output_root, configuration.screens]);
    if (key === configurationKey) return;
    const previousId = activeId;
    configurationKey = key; generation += 1; states.clear();
    const selector = byId("screen-selector"); selector.replaceChildren();
    const screens = configuration.ready ? configuration.screens : [];
    configuredScreens = screens;
    screens.forEach(screen => {
      const option = document.createElement("option"); option.value = screen.id;
      option.textContent = `${screen.name}${screen.enabled ? "" : " (disabled)"}`;
      selector.append(option);
    });
    selector.disabled = !screens.length;
    selector.value = screens.some(screen => screen.id === previousId) ? previousId : screens[0]?.id || "";
    activate(selector.value);
  }

  byId("screen-selector").addEventListener("change", event => activate(event.target.value));
  byId("results-search").addEventListener("input", event => {
    if (!state()) return; state().query = event.target.value; renderTable();
  });
  document.querySelectorAll("[data-result-tab]").forEach(button => button.addEventListener("click", () => {
    if (!state()) return; state().tab = button.dataset.resultTab; renderTable();
  }));
  document.querySelectorAll("[data-result-sort]").forEach(button => button.addEventListener("click", () => {
    const s = state(); if (!s) return;
    s.ascending = s.sort === button.dataset.resultSort ? !s.ascending : true;
    s.sort = button.dataset.resultSort; renderTable();
  }));
  byId("select-visible").addEventListener("click", () => {
    const s = state(); visibleRows(s).forEach(item => s.selected.add(item.ticker)); renderTable();
  });
  byId("clear-selection").addEventListener("click", () => { state().selected.clear(); renderTable(); });
  byId("update-results").addEventListener("click", () => {
    const s = state(); if (!s?.pending || s.error) return;
    adopt(s, s.pending); byId("export-feedback").textContent = "Loaded new results; all current stocks selected.";
    renderMeta(); renderTable();
  });
  byId("copy-selected").addEventListener("click", async () => {
    const text = exportText(state()); if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      byId("export-feedback").textContent = "Watchlist copied.";
    } catch {
      byId("export-feedback").textContent = "Clipboard unavailable. Copy the selected preview manually with Ctrl+C (Command+C on Mac).";
      byId("watchlist-preview").focus(); byId("watchlist-preview").select();
    }
  });
  byId("download-selected").addEventListener("click", () => {
    const text = exportText(state()); if (!text) return;
    const url = URL.createObjectURL(new Blob([text], {type: "text/plain;charset=utf-8"}));
    const link = document.createElement("a"); link.href = url; link.download = `${activeId}-selected.txt`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  window.resultsWorkspace = {configure, refresh: refreshResults};
})();
