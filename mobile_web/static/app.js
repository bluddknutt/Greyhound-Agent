(() => {
  const state = {
    deferredInstallPrompt: null,
    currentSource: window.APP_DEFAULTS?.source || "csv",
    latestResult: null,
    history: [],
    performance: { total_bets: 0, strike_rate: 0, roi: 0, profit_loss: 0 },
  };

  const els = {
    installBtn: document.getElementById("installBtn"),
    refreshBtn: document.getElementById("refreshBtn"),
    runForm: document.getElementById("runForm"),
    runBtn: document.getElementById("runBtn"),
    sourceNote: document.getElementById("sourceNote"),
    date: document.getElementById("date"),
    venue: document.getElementById("venue"),
    csvDirField: document.getElementById("csvDirField"),
    csvDir: document.getElementById("csv_dir"),
    dryRun: document.getElementById("dry_run"),
    statusPill: document.getElementById("statusPill"),
    statusText: document.getElementById("statusText"),
    statRaces: document.getElementById("statRaces"),
    statBets: document.getElementById("statBets"),
    statStaked: document.getElementById("statStaked"),
    statRoi: document.getElementById("statRoi"),
    bets: document.getElementById("bets"),
    races: document.getElementById("races"),
    history: document.getElementById("history"),
    tabs: Array.from(document.querySelectorAll(".tab")),
    sourceButtons: Array.from(document.querySelectorAll(".segment")),
    dateButtons: Array.from(document.querySelectorAll("[data-date-offset]")),
    emptyStateTemplate: document.getElementById("emptyStateTemplate"),
  };

  function cloneEmptyState() {
    return els.emptyStateTemplate.content.firstElementChild.cloneNode(true);
  }

  function setStatus(kind, text) {
    els.statusPill.className = `pill ${kind}`;
    els.statusPill.textContent = kind === "running" ? "Running" : kind === "success" ? "Done" : kind === "error" ? "Error" : "Ready";
    els.statusText.textContent = text;
  }

  function toMoney(value) {
    const amount = Number(value || 0);
    return `$${amount.toFixed(2)}`;
  }

  function toPercent(value, digits = 1) {
    const pct = Number(value || 0) * 100;
    return `${pct.toFixed(digits)}%`;
  }

  function valueOrDash(value) {
    if (value === null || value === undefined || value === "") {
      return "—";
    }
    return value;
  }

  function sourceHint(source) {
    if (source === "tab") {
      return "TAB API can fail outside Australia because access may be IP restricted.";
    }
    if (source === "scrape") {
      return "Scrape mode depends on thedogs.com.au availability and site layout staying stable.";
    }
    return "Best for local files in race_data/ or another folder on the server.";
  }

  function updateSourceUi(source) {
    state.currentSource = source;
    els.sourceButtons.forEach((button) => {
      button.classList.toggle("active", button.dataset.source === source);
    });
    els.sourceNote.textContent = sourceHint(source);
    els.csvDirField.classList.toggle("hidden-field", source !== "csv" && source !== "scrape");
    persistForm();
  }

  function formPayload() {
    return {
      source: state.currentSource,
      date: els.date.value || null,
      venue: els.venue.value.trim() || null,
      csv_dir: els.csvDir.value.trim() || "./race_data/",
      dry_run: els.dryRun.checked,
    };
  }

  function persistForm() {
    localStorage.setItem("greyhound-mobile-form", JSON.stringify(formPayload()));
  }

  function restoreForm() {
    const saved = localStorage.getItem("greyhound-mobile-form");
    if (!saved) {
      updateSourceUi(state.currentSource);
      return;
    }

    try {
      const payload = JSON.parse(saved);
      if (payload.source) {
        updateSourceUi(payload.source);
      }
      if (payload.date) {
        els.date.value = payload.date;
      }
      els.venue.value = payload.venue || "";
      els.csvDir.value = payload.csv_dir || "./race_data/";
      els.dryRun.checked = Boolean(payload.dry_run);
    } catch {
      updateSourceUi(state.currentSource);
    }
  }

  async function getJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || `Request failed with status ${response.status}`);
    }
    return data;
  }

  function renderSummary(result, performance) {
    const summary = result?.summary || {};
    els.statRaces.textContent = String(summary.races || 0);
    els.statBets.textContent = String(summary.bets || 0);
    els.statStaked.textContent = toMoney(summary.total_staked || 0);
    els.statRoi.textContent = toPercent(performance?.roi || 0);
  }

  function renderBets(bets) {
    els.bets.innerHTML = "";
    if (!bets || !bets.length) {
      els.bets.appendChild(cloneEmptyState());
      return;
    }

    bets.forEach((bet) => {
      const card = document.createElement("article");
      card.className = "result-card bet-card";
      card.innerHTML = `
        <div class="row-top">
          <div>
            <p class="eyebrow">${valueOrDash(bet.venue)} · Race ${valueOrDash(bet.race_number)}</p>
            <h3>${valueOrDash(bet.dog_name)}</h3>
          </div>
          <span class="badge">Box ${valueOrDash(bet.box)}</span>
        </div>
        <dl class="meta-grid">
          <div><dt>Model</dt><dd>${toPercent(bet.model_prob || 0)}</dd></div>
          <div><dt>Odds</dt><dd>${bet.odds ? toMoney(bet.odds) : "N/A"}</dd></div>
          <div><dt>Overlay</dt><dd>${bet.overlay_pct ? `${Number(bet.overlay_pct).toFixed(1)}%` : "N/A"}</dd></div>
          <div><dt>Stake</dt><dd>${toMoney(bet.bet_amount || 0)}</dd></div>
        </dl>
      `;
      els.bets.appendChild(card);
    });
  }

  function renderRaces(predictions) {
    els.races.innerHTML = "";
    if (!predictions || !predictions.length) {
      els.races.appendChild(cloneEmptyState());
      return;
    }

    predictions.forEach((race) => {
      const card = document.createElement("article");
      card.className = "result-card";

      const runners = (race.runners || []).map((runner) => `
        <div class="runner-row">
          <span class="runner-rank">#${valueOrDash(runner.rank)}</span>
          <div class="runner-main">
            <strong>${valueOrDash(runner.dog_name)}</strong>
            <small>Box ${valueOrDash(runner.box)}</small>
          </div>
          <span>${toPercent(runner.model_prob || 0)}</span>
          <span>${runner.odds ? toMoney(runner.odds) : "N/A"}</span>
        </div>
      `).join("");

      card.innerHTML = `
        <div class="row-top">
          <div>
            <p class="eyebrow">${valueOrDash(race.venue)}</p>
            <h3>Race ${valueOrDash(race.race_number)}</h3>
          </div>
          <span class="badge">${(race.runners || []).length} runners</span>
        </div>
        <div class="runner-table">
          ${runners}
        </div>
      `;
      els.races.appendChild(card);
    });
  }

  function renderHistory(history, performance) {
    els.history.innerHTML = "";
    const perf = document.createElement("article");
    perf.className = "result-card";
    perf.innerHTML = `
      <div class="row-top">
        <div>
          <p class="eyebrow">Overall performance</p>
          <h3>${valueOrDash(performance.total_bets)} bets</h3>
        </div>
        <span class="badge">${toPercent(performance.strike_rate || 0)}</span>
      </div>
      <dl class="meta-grid">
        <div><dt>Strike</dt><dd>${toPercent(performance.strike_rate || 0)}</dd></div>
        <div><dt>ROI</dt><dd>${toPercent(performance.roi || 0)}</dd></div>
        <div><dt>P/L</dt><dd>${toMoney(performance.profit_loss || 0)}</dd></div>
        <div><dt>Settled bets</dt><dd>${valueOrDash(performance.total_bets)}</dd></div>
      </dl>
    `;
    els.history.appendChild(perf);

    if (!history || !history.length) {
      els.history.appendChild(cloneEmptyState());
      return;
    }

    history.forEach((item) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "result-card history-card";
      card.dataset.runId = item.run_id;
      card.innerHTML = `
        <div class="row-top">
          <div>
            <p class="eyebrow">Run #${item.run_id}</p>
            <h3>${valueOrDash(item.run_date)} · ${valueOrDash(item.source)}</h3>
          </div>
          <span class="badge ${item.status === "success" ? "good" : "bad"}">${valueOrDash(item.status)}</span>
        </div>
        <dl class="meta-grid">
          <div><dt>Races</dt><dd>${valueOrDash(item.summary?.races || 0)}</dd></div>
          <div><dt>Bets</dt><dd>${valueOrDash(item.summary?.bets || 0)}</dd></div>
          <div><dt>Venue</dt><dd>${valueOrDash(item.venue_filter || "All")}</dd></div>
          <div><dt>Dry run</dt><dd>${item.dry_run ? "Yes" : "No"}</dd></div>
        </dl>
      `;
      card.addEventListener("click", async () => {
        try {
          setStatus("running", `Loading run #${item.run_id}...`);
          const data = await getJson(`/api/results/${item.run_id}`);
          applyRun(data.result, false);
          activateTab("bets");
          setStatus("success", `Loaded run #${item.run_id}.`);
        } catch (error) {
          setStatus("error", error.message);
        }
      });
      els.history.appendChild(card);
    });
  }

  function applyRun(result, persist = true) {
    state.latestResult = result;
    renderSummary(result, state.performance);
    renderBets(result?.selected_bets || []);
    renderRaces(result?.predictions || []);
    if (persist) {
      localStorage.setItem("greyhound-mobile-last-run", JSON.stringify(result));
    }
  }

  function restoreLastRun() {
    const raw = localStorage.getItem("greyhound-mobile-last-run");
    if (!raw) {
      renderBets([]);
      renderRaces([]);
      return;
    }

    try {
      applyRun(JSON.parse(raw), false);
    } catch {
      renderBets([]);
      renderRaces([]);
    }
  }

  function activateTab(tabName) {
    els.tabs.forEach((button) => {
      button.classList.toggle("active", button.dataset.tab === tabName);
    });

    ["bets", "races", "history"].forEach((panelName) => {
      const panel = document.getElementById(panelName);
      panel.classList.toggle("hidden", panelName !== tabName);
    });

    localStorage.setItem("greyhound-mobile-tab", tabName);
  }

  async function loadLatest() {
    const data = await getJson("/api/results/latest");
    state.performance = data.performance || state.performance;
    if (data.result) {
      applyRun(data.result, false);
    } else {
      renderSummary(null, state.performance);
      renderBets([]);
      renderRaces([]);
    }
  }

  async function loadHistory() {
    const data = await getJson("/api/results/history");
    state.history = data.history || [];
    state.performance = data.performance || state.performance;
    renderHistory(state.history, state.performance);
    if (!state.latestResult) {
      renderSummary(null, state.performance);
    } else {
      renderSummary(state.latestResult, state.performance);
    }
  }

  async function submitRun(event) {
    event.preventDefault();
    persistForm();
    els.runBtn.disabled = true;
    setStatus("running", "Pipeline is running. This can take a while for live sources.");

    try {
      const data = await getJson("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formPayload()),
      });

      state.performance = data.performance || state.performance;
      applyRun(data.result);
      await loadHistory();
      activateTab("bets");
      const summary = data.result?.summary || {};
      setStatus("success", `Finished: ${summary.races || 0} races, ${summary.bets || 0} bets.`);
    } catch (error) {
      setStatus("error", error.message);
      await loadHistory();
    } finally {
      els.runBtn.disabled = false;
    }
  }

  function applyDateOffset(offsetDays) {
    const base = new Date();
    base.setDate(base.getDate() + offsetDays);
    const iso = base.toISOString().slice(0, 10);
    els.date.value = iso;
    persistForm();
  }

  function setupInstallPrompt() {
    window.addEventListener("beforeinstallprompt", (event) => {
      event.preventDefault();
      state.deferredInstallPrompt = event;
      els.installBtn.classList.remove("hidden");
    });

    els.installBtn.addEventListener("click", async () => {
      if (!state.deferredInstallPrompt) {
        return;
      }
      state.deferredInstallPrompt.prompt();
      await state.deferredInstallPrompt.userChoice;
      state.deferredInstallPrompt = null;
      els.installBtn.classList.add("hidden");
    });
  }

  function setupServiceWorker() {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/service-worker.js").catch(() => {});
    }
  }

  function wireEvents() {
    els.runForm.addEventListener("submit", submitRun);
    els.refreshBtn.addEventListener("click", async () => {
      setStatus("running", "Refreshing latest data...");
      try {
        await loadLatest();
        await loadHistory();
        setStatus("success", "Latest data refreshed.");
      } catch (error) {
        setStatus("error", error.message);
      }
    });

    els.sourceButtons.forEach((button) => {
      button.addEventListener("click", () => updateSourceUi(button.dataset.source));
    });

    [els.date, els.venue, els.csvDir, els.dryRun].forEach((element) => {
      element.addEventListener("change", persistForm);
      element.addEventListener("input", persistForm);
    });

    els.dateButtons.forEach((button) => {
      button.addEventListener("click", () => applyDateOffset(Number(button.dataset.dateOffset || 0)));
    });

    els.tabs.forEach((button) => {
      button.addEventListener("click", () => activateTab(button.dataset.tab));
    });
  }

  async function init() {
    restoreForm();
    restoreLastRun();
    wireEvents();
    setupInstallPrompt();
    setupServiceWorker();

    const savedTab = localStorage.getItem("greyhound-mobile-tab") || "bets";
    activateTab(savedTab);

    try {
      await loadLatest();
      await loadHistory();
      setStatus("idle", "Ready.");
    } catch (error) {
      setStatus("error", error.message);
    }
  }

  init();
})();
