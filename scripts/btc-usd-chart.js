(function (root, factory) {
  const chart = factory();
  if (typeof module === "object" && module.exports) module.exports = chart;
  if (root) root.BTCUSDChart = chart;
})(typeof globalThis === "undefined" ? this : globalThis, function () {
  "use strict";

  const SOURCE_URL = "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=21600";
  const GRANULARITY_SECONDS = 6 * 60 * 60;
  const CHART_SECONDS = 12 * 60 * 60;
  const FETCH_TIMEOUT_MS = 10000;
  const LIBRARY_URL = "https://unpkg.com/lightweight-charts@5.2.1/dist/lightweight-charts.standalone.production.js";
  const LIBRARY_TIMEOUT_MS = 10000;

  function aggregateTwelveHourCandles(rows, nowSeconds = Date.now() / 1000) {
    if (!Array.isArray(rows)) throw new Error("Coinbase candle response must be an array");

    const sixHourCandles = rows.map((row) => {
      if (!Array.isArray(row) || row.length < 6) throw new Error("Coinbase returned a malformed candle");
      const [timeValue, lowValue, highValue, openValue, closeValue, volumeValue] = row;
      const time = Number(timeValue);
      const low = Number(lowValue);
      const high = Number(highValue);
      const open = Number(openValue);
      const close = Number(closeValue);
      const volume = Number(volumeValue);
      if (!Number.isInteger(time) || ![low, high, open, close, volume].every(Number.isFinite) ||
          [low, high, open, close].some((price) => price <= 0) || volume < 0 ||
          low > Math.min(open, close) || high < Math.max(open, close) || low > high) {
        throw new Error("Coinbase returned invalid OHLCV values");
      }
      return { time, low, high, open, close, volume };
    }).sort((a, b) => a.time - b.time).slice(-300);

    for (let index = 1; index < sixHourCandles.length; index += 1) {
      if (sixHourCandles[index].time === sixHourCandles[index - 1].time) {
        throw new Error("Coinbase returned duplicate candle timestamps");
      }
    }

    const completeCandles = sixHourCandles.filter((candle) => candle.time + GRANULARITY_SECONDS <= nowSeconds);
    const byTime = new Map(completeCandles.map((candle) => [candle.time, candle]));
    const aggregated = [];
    for (const first of completeCandles) {
      if (first.time % CHART_SECONDS !== 0) continue;
      const second = byTime.get(first.time + GRANULARITY_SECONDS);
      if (!second) continue;
      if (second.time + GRANULARITY_SECONDS > nowSeconds) continue;
      aggregated.push({
        time: first.time,
        open: first.open,
        high: Math.max(first.high, second.high),
        low: Math.min(first.low, second.low),
        close: second.close
      });
    }
    if (aggregated.length === 0) throw new Error("No complete, contiguous 12-hour candles are available");
    return aggregated;
  }

  function setStatus(element, status, text) {
    if (!element) return;
    element.dataset.status = status;
    element.textContent = text;
  }

  async function fetchCandles(fetchImpl, options = {}) {
    if (typeof fetchImpl !== "function") throw new Error("Browser fetch is unavailable");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeoutMs || FETCH_TIMEOUT_MS);
    try {
      const response = await fetchImpl(options.url || SOURCE_URL, {
        cache: "no-store",
        signal: controller.signal
      });
      if (!response.ok) throw new Error(`Coinbase candle request failed (HTTP ${response.status})`);
      return aggregateTwelveHourCandles(await response.json(), options.nowSeconds);
    } finally {
      clearTimeout(timeout);
    }
  }

  function loadLibrary(doc, timeoutMs = LIBRARY_TIMEOUT_MS) {
    if (typeof LightweightCharts !== "undefined" && LightweightCharts.createChart) {
      return Promise.resolve(LightweightCharts);
    }
    return new Promise((resolve, reject) => {
      const script = doc.createElement("script");
      let settled = false;
      const timeout = setTimeout(() => {
        if (settled) return;
        settled = true;
        script.remove();
        reject(new Error("TradingView chart library timed out"));
      }, timeoutMs);
      const finish = (error, library) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        script.onload = null;
        script.onerror = null;
        if (error) reject(error);
        else resolve(library);
      };
      script.async = true;
      script.crossOrigin = "anonymous";
      script.src = LIBRARY_URL;
      script.onload = () => {
        const library = typeof LightweightCharts === "undefined" ? null : LightweightCharts;
        if (!library || !library.createChart) finish(new Error("TradingView chart library did not initialize"));
        else finish(null, library);
      };
      script.onerror = () => finish(new Error("TradingView chart library could not be downloaded"));
      doc.head.appendChild(script);
    });
  }

  function createController(options = {}) {
    const doc = options.document || (typeof document !== "undefined" ? document : null);
    const container = options.container || (doc && doc.getElementById("btc-usd-chart-canvas"));
    const status = options.status || (doc && doc.getElementById("btc-usd-chart-status"));
    const fetchImpl = options.fetch || (typeof fetch === "function" ? fetch.bind(globalThis) : null);
    let library = options.library || (typeof LightweightCharts !== "undefined" ? LightweightCharts : null);
    let chart = null;
    let started = false;

    return {
      async start() {
        if (started) return;
        started = true;
        if (!container || !doc) {
          setStatus(status, "error", "Chart unavailable: the chart container is missing.");
          return;
        }
        setStatus(status, "loading", "Loading Coinbase BTC-USD 12-hour candles…");
        try {
          const [candles] = await Promise.all([
            fetchCandles(fetchImpl, { nowSeconds: options.nowSeconds }),
            library ? Promise.resolve(library) : loadLibrary(doc, options.libraryTimeoutMs)
          ]);
          if (!library) library = typeof LightweightCharts === "undefined" ? null : LightweightCharts;
          if (!library || typeof library.createChart !== "function" || !library.CandlestickSeries) {
            throw new Error("TradingView chart library could not be initialized");
          }
          chart = library.createChart(container, {
            autoSize: true,
            layout: {
              background: { type: "solid", color: "#020403" },
              textColor: "#a2ffdc"
            },
            grid: {
              vertLines: { color: "rgba(0, 245, 160, 0.10)" },
              horzLines: { color: "rgba(0, 245, 160, 0.10)" }
            },
            crosshair: { mode: library.CrosshairMode ? library.CrosshairMode.Normal : 0 },
            rightPriceScale: { borderColor: "rgba(0, 245, 160, 0.22)" },
            timeScale: { borderColor: "rgba(0, 245, 160, 0.22)", timeVisible: true },
            localization: { locale: "en-US" }
          });
          const series = chart.addSeries(library.CandlestickSeries, {
            upColor: "#00f5a0",
            downColor: "#ff747d",
            borderVisible: false,
            wickUpColor: "#00f5a0",
            wickDownColor: "#ff747d",
            priceFormat: { type: "price", precision: 2, minMove: 0.01 }
          });
          series.setData(candles);
          chart.timeScale().fitContent();
          setStatus(status, "loaded", `Loaded ${candles.length} complete 12-hour BTC-USD candles from Coinbase Exchange. The latest candle may be several hours old.`);
        } catch (error) {
          setStatus(status, "error", `Chart unavailable: ${error.message}. No synthetic candles are displayed.`);
        }
      },
      destroy() {
        if (chart) chart.remove();
        chart = null;
      }
    };
  }

  return { createController, aggregateTwelveHourCandles, fetchCandles, sourceUrl: SOURCE_URL };
});
