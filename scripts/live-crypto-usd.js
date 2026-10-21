(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.LiveCryptoUSD = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const SYMBOLS = ["ETH", "SOL"];
  const REFRESH_INTERVAL_MS = 60_000;
  const REQUEST_TIMEOUT_MS = 10_000;

  function endpointFor(symbol) {
    if (!SYMBOLS.includes(symbol)) throw new TypeError("Unsupported cryptocurrency symbol");
    return `https://api.exchange.coinbase.com/products/${symbol}-USD/ticker`;
  }

  function formatUSDPrice(value) {
    if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
      throw new TypeError("USD price must be a finite positive number");
    }
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 6
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
    const assets = Object.create(null);

    for (const symbol of SYMBOLS) {
      assets[symbol] = {
        inFlight: false,
        lastSuccess: null,
        intervalId: null,
        activeController: null
      };
    }

    async function refresh(symbol) {
      if (!SYMBOLS.includes(symbol)) throw new TypeError("Unsupported cryptocurrency symbol");
      const asset = assets[symbol];
      if (asset.inFlight) return false;
      asset.inFlight = true;
      const requestController = new AbortController();
      asset.activeController = requestController;
      let timedOut = false;
      const timeoutId = scheduleTimeout(() => {
        timedOut = true;
        requestController.abort();
      }, REQUEST_TIMEOUT_MS);

      if (asset.lastSuccess) onState(symbol, { ...asset.lastSuccess, status: "refreshing", error: null });
      else onState(symbol, { status: "loading", price: null, sourceTime: null, receivedAt: null, error: null });

      try {
        const response = await fetchImpl(endpointFor(symbol), {
          method: "GET",
          headers: { Accept: "application/json" },
          signal: requestController.signal
        });
        if (!response || !response.ok) throw new Error(`HTTP ${response ? response.status : "unknown"}`);
        const ticker = parseTicker(await response.json());
        const receivedAt = now();
        if (!(receivedAt instanceof Date) || !Number.isFinite(receivedAt.getTime())) {
          throw new TypeError("Local update timestamp is invalid");
        }
        asset.lastSuccess = { ...ticker, receivedAt };
        onState(symbol, { ...asset.lastSuccess, status: "live", error: null });
        return true;
      } catch (error) {
        const message = timedOut ? "Request timed out" : (error && error.message ? error.message : "Request failed");
        if (asset.lastSuccess) onState(symbol, { ...asset.lastSuccess, status: "stale", error: message });
        else onState(symbol, { status: "error", price: null, sourceTime: null, receivedAt: null, error: message });
        return false;
      } finally {
        cancelTimeout(timeoutId);
        asset.activeController = null;
        asset.inFlight = false;
      }
    }

    function start() {
      const starts = SYMBOLS.map((symbol) => {
        const asset = assets[symbol];
        if (asset.intervalId !== null) return Promise.resolve(false);
        const initialRequest = refresh(symbol);
        asset.intervalId = scheduleInterval(() => { void refresh(symbol); }, REFRESH_INTERVAL_MS);
        return initialRequest;
      });
      return Promise.all(starts);
    }

    function stop() {
      for (const symbol of SYMBOLS) {
        const asset = assets[symbol];
        if (asset.intervalId !== null) {
          cancelInterval(asset.intervalId);
          asset.intervalId = null;
        }
        if (asset.activeController) asset.activeController.abort();
      }
    }

    return { refresh, start, stop };
  }

  return { SYMBOLS, REFRESH_INTERVAL_MS, REQUEST_TIMEOUT_MS, endpointFor, formatUSDPrice, parseTicker, createController };
});
