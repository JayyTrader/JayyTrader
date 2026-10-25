(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.MVRVScore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const DATA_URL = "data/mvrv-z-score.json";
  const REFRESH_MS = 15 * 60 * 1000;

  function validPayload(payload) {
    if (!payload || !payload.latest || !["available", "snapshot_only"].includes(payload.status)) return false;
    const latest = payload.latest;
    return typeof latest.date === "string"
      && Number.isFinite(latest.rawValue)
      && Number.isFinite(latest.historicalPercentile)
      && latest.historicalPercentile >= 0
      && latest.historicalPercentile <= 100
      && Number.isFinite(latest.score)
      && latest.score >= -2
      && latest.score <= 2;
  }

  function formatScore(value) {
    if (!Number.isFinite(value)) return "—";
    return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
  }

  function formatRaw(value) {
    if (!Number.isFinite(value)) return "—";
    return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
  }

  function isStale(dateText, now = new Date(), maxAgeDays = 3) {
    if (typeof dateText !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(dateText)) return true;
    const observed = new Date(`${dateText}T00:00:00Z`);
    if (Number.isNaN(observed.getTime()) || observed.getTime() > now.getTime()) return true;
    return now.getTime() - observed.getTime() > maxAgeDays * 86400000;
  }

  function createController(options = {}) {
    const fetchImpl = options.fetchImpl || (typeof fetch === "function" ? fetch.bind(globalThis) : null);
    const onState = typeof options.onState === "function" ? options.onState : () => {};
    let timer = null;
    let stopped = false;

    async function refresh() {
      if (!fetchImpl || stopped) return;
      try {
        const response = await fetchImpl(DATA_URL, { cache: "no-store" });
        if (!response || !response.ok) throw new Error(`HTTP ${response ? response.status : "unavailable"}`);
        const payload = await response.json();
        if (!validPayload(payload)) throw new Error("MVRV data failed client-side validation");
        const stale = isStale(payload.latest.date);
        onState({
          status: stale ? "stale" : payload.status === "snapshot_only" ? "snapshot" : "available",
          payload,
          error: null,
          stale
        });
      } catch (error) {
        onState({ status: "error", payload: null, error: String(error && error.message ? error.message : error), stale: true });
      }
    }

    return {
      start() {
        stopped = false;
        void refresh();
        if (timer !== null) clearInterval(timer);
        timer = setInterval(() => void refresh(), REFRESH_MS);
        return this;
      },
      refresh,
      stop() {
        stopped = true;
        if (timer !== null) clearInterval(timer);
        timer = null;
      }
    };
  }

  return { DATA_URL, REFRESH_MS, validPayload, formatScore, formatRaw, isStale, createController };
});
