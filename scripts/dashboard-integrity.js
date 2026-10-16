/* Shared dashboard validation helpers (also exercised by Node's test runner). */
(function (root) {
  "use strict";

  function validateScore(score, label = "score") {
    if (typeof score !== "number" || !Number.isFinite(score) || score < -3 || score > 3) {
      throw new TypeError(`${label} must be a finite number from -3 to +3`);
    }
    return score;
  }

  function compositeMarkerPercent(score) {
    if (score === null || score === undefined) return null;
    validateScore(score, "composite score");
    return ((3 - score) / 6) * 100;
  }

  function validateHistory(history) {
    if (!Array.isArray(history)) throw new TypeError("History must be an array");
    const seen = new Set();
    let previous = "";
    history.forEach((point, index) => {
      if (!point || typeof point !== "object" || Array.isArray(point)) {
        throw new TypeError(`History entry ${index} must be an object`);
      }
      if (typeof point.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(point.date)) {
        throw new TypeError(`History entry ${index} must have a YYYY-MM-DD date`);
      }
      const parsed = new Date(`${point.date}T00:00:00Z`);
      if (!Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== point.date) {
        throw new TypeError(`History entry ${index} has an invalid calendar date`);
      }
      if (seen.has(point.date)) throw new TypeError(`Duplicate history date: ${point.date}`);
      if (previous && point.date <= previous) throw new TypeError("History dates must be strictly chronological");
      validateScore(point.score, `history score for ${point.date}`);
      seen.add(point.date);
      previous = point.date;
    });
    return history;
  }

  function validateTimestamp(value, label) {
    if (typeof value !== "string") throw new TypeError(`${label} must be a string`);
    const epoch = /^\d{10}$/.test(value) ? Number(value) * 1000 : value;
    if (!Number.isFinite(new Date(epoch).getTime())) throw new TypeError(`${label} is invalid`);
  }

  function validateData(data, expectedNames) {
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      throw new TypeError("Data must be an object");
    }
    if (data.updatedAt !== undefined && data.updatedAt !== null) validateTimestamp(data.updatedAt, "updatedAt");
    if (!Array.isArray(data.indicators) || data.indicators.length !== expectedNames.length) {
      throw new TypeError(`Expected ${expectedNames.length} indicators`);
    }
    const actualNames = data.indicators.map((item) => item && item.name);
    if (actualNames.some((name) => typeof name !== "string") || new Set(actualNames).size !== expectedNames.length) {
      throw new TypeError("Indicator names must be unique strings");
    }
    const expected = new Set(expectedNames);
    if (actualNames.some((name) => !expected.has(name)) || expectedNames.some((name) => !actualNames.includes(name))) {
      throw new TypeError("Indicator set does not match the dashboard");
    }
    data.indicators.forEach((item, index) => {
      if (!item || typeof item !== "object" || Array.isArray(item)) {
        throw new TypeError(`Indicator ${index} must be an object`);
      }
      if (typeof item.category !== "string") throw new TypeError(`Category for ${item.name} must be a string`);
      if (item.score !== null && item.score !== undefined) validateScore(item.score, `score for ${item.name}`);
      if (item.rawValue !== null && item.rawValue !== undefined &&
          (typeof item.rawValue !== "number" || !Number.isFinite(item.rawValue))) {
        throw new TypeError(`Raw reading for ${item.name} must be finite or null`);
      }
      if (item.source !== null && item.source !== undefined &&
          (typeof item.source !== "string" || !/^https:\/\//i.test(item.source))) {
        throw new TypeError(`Source for ${item.name} must be an HTTPS URL`);
      }
      if (item.lastUpdated !== null && item.lastUpdated !== undefined && typeof item.lastUpdated !== "string") {
        throw new TypeError(`Timestamp for ${item.name} must be a string or null`);
      }
      if (item.lastUpdated !== null && item.lastUpdated !== undefined) validateTimestamp(item.lastUpdated, `Timestamp for ${item.name}`);
    });
    if (data.compositeScore !== null && data.compositeScore !== undefined) {
      validateScore(data.compositeScore, "composite score");
    }
    if (data.feedFailures !== undefined && !Array.isArray(data.feedFailures)) {
      throw new TypeError("Feed failures must be an array");
    }
    if (data.feedFailures) data.feedFailures.forEach((failure, index) => {
      if (!failure || typeof failure.feed !== "string" || typeof failure.type !== "string" || typeof failure.message !== "string") {
        throw new TypeError(`Feed failure ${index} is malformed`);
      }
    });
    if (data.bitcoinPriceUSDT !== undefined) {
      const quote = data.bitcoinPriceUSDT;
      if (!quote || typeof quote !== "object" ||
          (quote.usdt !== null && quote.usdt !== undefined &&
           (typeof quote.usdt !== "number" || !Number.isFinite(quote.usdt) || quote.usdt <= 0))) {
        throw new TypeError("BTC/USDT daily close is malformed");
      }
    }
    return data;
  }

  const api = { validateScore, compositeMarkerPercent, validateHistory, validateTimestamp, validateData };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.SDCAIntegrity = api;
})(typeof window !== "undefined" ? window : globalThis);
