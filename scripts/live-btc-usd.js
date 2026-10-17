(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.LiveBTCUSD = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const ENDPOINT = "https://api.exchange.coinbase.com/products/BTC-USD/ticker";
  const REFRESH_INTERVAL_MS = 60_000;
  const REQUEST_TIMEOUT_MS = 10_000;

  function formatUSDPrice(value) {
    if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
      throw new TypeError("BTC/USD price must be a finite positive number");
    }
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(value);
  }

  function parseTicker(payload) {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      throw new TypeError("Coinbase ticker response must be an object");
    }
    if (typeof payload.price !== "string" || payload.price.trim() === "") {
      throw new TypeError("Coinbase ticker response is missing its price");
    }
    const price = Number(payload.price);
    if (!Number.isFinite(price) || price <= 0) {
      throw new TypeError("Coinbase ticker price must be finite and positive");
    }
    if (typeof payload.time !== "string" || !Number.isFinite(Date.parse(payload.time))) {
      throw new TypeError("Coinbase ticker response has an invalid trade timestamp");
    }
    return { price, sourceTime: new Date(payload.time).toISOString() };
  }

  function createController(options = {}) {
    const fetchImpl = options.fetchImpl || (typeof fetch === "function" ? fetch.bind(globalThis) : null);
    if (typeof fetchImpl !== "function") throw new TypeError("A fetch implementation is required");
    const onState = typeof options.onState === "function" ? options.onState : () => {};
    const now = typeof options.now === "function" ? options.now : () => new Date();
    const scheduleInterval = options.setIntervalImpl || setInterval;
    const cancelInterval = options.clearIntervalImpl || clearInterval;
    const scheduleTimeout = options.setTimeoutImpl || setTimeout;
    const cancelTimeout = options.clearTimeoutImpl || clearTimeout;

    let inFlight = false;
    let lastSuccess = null;
    let intervalId = null;
    let activeController = null;

    async function refresh() {
      if (inFlight) return false;
      inFlight = true;
      const requestController = new AbortController();
      activeController = requestController;
      let timedOut = false;
      const timeoutId = scheduleTimeout(() => {
        timedOut = true;
        requestController.abort();
      }, REQUEST_TIMEOUT_MS);

      if (lastSuccess) onState({ ...lastSuccess, status: "refreshing", error: null });
      else onState({ status: "loading", price: null, sourceTime: null, receivedAt: null, error: null });

      try {
        const response = await fetchImpl(ENDPOINT, {
          method: "GET",
          headers: { Accept: "application/json" },
          signal: requestController.signal
        });
        if (!response || !response.ok) {
          throw new Error(`HTTP ${response ? response.status : "unknown"}`);
        }
        const ticker = parseTicker(await response.json());
        const receivedAt = now();
        if (!(receivedAt instanceof Date) || !Number.isFinite(receivedAt.getTime())) {
          throw new TypeError("Local update timestamp is invalid");
        }
        lastSuccess = { ...ticker, receivedAt };
        onState({ ...lastSuccess, status: "live", error: null });
        return true;
      } catch (error) {
        const message = timedOut ? "Request timed out" : (error && error.message ? error.message : "Request failed");
        if (lastSuccess) onState({ ...lastSuccess, status: "stale", error: message });
        else onState({ status: "error", price: null, sourceTime: null, receivedAt: null, error: message });
        return false;
      } finally {
        cancelTimeout(timeoutId);
        activeController = null;
        inFlight = false;
      }
    }

    function start() {
      if (intervalId !== null) return Promise.resolve(false);
      const initialRequest = refresh();
      intervalId = scheduleInterval(() => { void refresh(); }, REFRESH_INTERVAL_MS);
      return initialRequest;
    }

    function stop() {
      if (intervalId !== null) {
        cancelInterval(intervalId);
        intervalId = null;
      }
      if (activeController) activeController.abort();
    }

    return { refresh, start, stop };
  }

  return { ENDPOINT, REFRESH_INTERVAL_MS, REQUEST_TIMEOUT_MS, formatUSDPrice, parseTicker, createController };
});
