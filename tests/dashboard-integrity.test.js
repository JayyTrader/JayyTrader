const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const integrity = require('../scripts/dashboard-integrity.js');
const liveBTCUSD = require('../scripts/live-btc-usd.js');

const names = Array.from({ length: 15 }, (_, index) => `indicator-${index}`);
const baseData = () => ({
  indicators: names.map((name) => ({ name, category: 'Test', score: null, rawValue: null })),
  compositeScore: null,
  feedFailures: []
});

test('missing composite has no marker position; real zero remains a valid zero', () => {
  assert.equal(integrity.compositeMarkerPercent(null), null);
  assert.equal(integrity.compositeMarkerPercent(undefined), null);
  assert.equal(integrity.compositeMarkerPercent(0), 50);
  assert.equal(integrity.compositeMarkerPercent(3), 0);
  assert.equal(integrity.compositeMarkerPercent(-3), 100);
});

test('composite and history values outside display range are rejected', () => {
  for (const value of [-3.001, 3.001, Infinity, NaN]) {
    assert.throws(() => integrity.compositeMarkerPercent(value), /finite number/);
  }
  assert.throws(() => integrity.validateHistory([{ date: '2025-01-01', score: 3.1 }]), /finite number/);
});

test('history requires real unique ISO dates in chronological order', () => {
  const valid = [{ date: '2025-01-01', score: -1 }, { date: '2025-01-03', score: 1 }];
  assert.equal(integrity.validateHistory(valid), valid);
  const badHistories = [
    [{ date: '2025-02-30', score: 0 }],
    [{ date: '2025-01-01T00:00:00Z', score: 0 }],
    [{ date: '2025-01-01', score: 0 }, { date: '2025-01-01', score: 0 }],
    [{ date: '2025-01-03', score: 0 }, { date: '2025-01-02', score: 0 }],
  ];
  for (const history of badHistories) assert.throws(() => integrity.validateHistory(history));
});

test('validateData checks history content and cross-checks pipeline history metadata', () => {
  const data = baseData();
  data.history = [{ date: '2025-01-01', score: 0 }];
  data.historyValidation = { valid: true, validCount: 1, error: null };
  assert.deepEqual(integrity.validateHistoryState(integrity.validateData(data, names)), { history: data.history, error: null });

  const countMismatch = { ...data, historyValidation: { valid: true, validCount: 0, error: null } };
  assert.match(integrity.validateHistoryState(integrity.validateData(countMismatch, names)).error, /count mismatch/);

  const contentMismatch = { ...data, history: [{ date: '2025-02-30', score: 0 }] };
  assert.match(integrity.validateHistoryState(integrity.validateData(contentMismatch, names)).error, /marked history valid/);

  const rejectedByPipeline = { ...data, historyValidation: { valid: false, validCount: 0, error: 'Duplicate history date' } };
  assert.deepEqual(integrity.validateHistoryState(integrity.validateData(rejectedByPipeline, names)), { history: [], error: 'Duplicate history date' });
});

test('data freshness comes from indicator source timestamps, not the pipeline run time', () => {
  const data = baseData();
  data.updatedAt = '2026-10-16T23:59:00Z';
  data.indicators[0] = { ...data.indicators[0], rawValue: 12, lastUpdated: '2026-10-15' };
  data.indicators[1] = { ...data.indicators[1], rawValue: 13, lastUpdated: '1792108800' };
  assert.equal(integrity.latestIndicatorTimestamp(data.indicators), '1792108800');
  assert.equal(integrity.latestIndicatorTimestamp(data.indicators.slice(2)), null);
});

test('freshness summaries preserve date-only observations and genuine timestamps', () => {
  const formatter = (value) => `formatted:${value}`;
  assert.equal(integrity.latestIndicatorTimestamp([
    { rawValue: 1, lastUpdated: '2026-10-15' },
    { rawValue: 2, lastUpdated: '2026-10-14T18:30:00Z' },
    { rawValue: null, lastUpdated: '2026-10-16' }
  ]), '2026-10-15');
  assert.equal(integrity.formatObservationTimestamp('2026-10-15', formatter), '2026-10-15 (UTC source date)');
  assert.equal(integrity.latestIndicatorTimestamp([
    { rawValue: 3, sourceTimestamp: '2026-10-15T18:30:00Z', lastUpdated: '2026-10-15' }
  ]), '2026-10-15T18:30:00Z');
  assert.equal(integrity.formatObservationTimestamp('2026-10-15T18:30:00Z', formatter), 'formatted:2026-10-15T18:30:00Z');
});

test('data schema rejects unknown, duplicate, missing indicators and invalid composite', () => {
  assert.equal(integrity.validateData(baseData(), names).indicators.length, 15);
  const duplicate = baseData();
  duplicate.indicators[1].name = duplicate.indicators[0].name;
  assert.throws(() => integrity.validateData(duplicate, names), /unique/);
  const missing = baseData();
  missing.indicators.pop();
  assert.throws(() => integrity.validateData(missing, names), /Expected/);
  const invalidComposite = baseData();
  invalidComposite.compositeScore = 4;
  assert.throws(() => integrity.validateData(invalidComposite, names), /finite number/);
  const invalidTimestamp = baseData();
  invalidTimestamp.updatedAt = 'not-a-timestamp';
  assert.throws(() => integrity.validateData(invalidTimestamp, names), /updatedAt is invalid/);
});

test('verified raw readings require valid provenance metadata and source timestamps', () => {
  const data = baseData();
  data.indicators[8] = {
    name: names[8], category: 'Technical', score: null, rawValue: 57.2915,
    status: 'raw_available_score_pending', source: 'https://coinsentry.app/api/v1/indicators.json',
    referenceSource: 'https://coinsentry.app/indicators/bitcoin-rsi',
    attributionUrl: 'https://coinsentry.app/', sourceTimestamp: '2026-10-15',
    lastUpdated: '2026-10-15', timeframe: 'weekly', verificationStatus: 'verified_field'
  };
  assert.equal(integrity.validateData(data, names).indicators[8].timeframe, 'weekly');
  const noTimestamp = structuredClone(data);
  delete noTimestamp.indicators[8].lastUpdated;
  assert.throws(() => integrity.validateData(noTimestamp, names), /Verified reading/);
  const noSourceTimestamp = structuredClone(data);
  delete noSourceTimestamp.indicators[8].sourceTimestamp;
  assert.throws(() => integrity.validateData(noSourceTimestamp, names), /Verified reading/);
  const badBacklink = structuredClone(data);
  badBacklink.indicators[8].attributionUrl = 'javascript:alert(1)';
  assert.throws(() => integrity.validateData(badBacklink, names), /HTTPS URL/);

  data.indicators[9] = {
    name: names[9], category: 'Technical', score: null, rawValue: 0.47,
    status: 'raw_available_score_pending', source: 'https://example.com/daily.csv',
    lastUpdated: '2026-10-15', sourceTimestamp: '2026-10-15', timeframe: 'daily',
    verificationStatus: 'verified_calculation', sourceComparison: {
      comparisonDate: '2026-10-09', calculatedValue: 0.459894, publishedValue: 0.46,
      displayPrecision: 3, matchedAtPublishedPrecision: true, source: 'https://example.com/chart'
    }
  };
  assert.equal(integrity.validateData(data, names).indicators[9].sourceComparison.publishedValue, 0.46);
  const noComparison = structuredClone(data);
  delete noComparison.indicators[9].sourceComparison;
  assert.throws(() => integrity.validateData(noComparison, names), /source comparison/);
  const mismatchedComparison = structuredClone(data);
  mismatchedComparison.indicators[9].sourceComparison.publishedValue = 0.47;
  assert.throws(() => integrity.validateData(mismatchedComparison, names), /does not match/);
});

test('dashboard hides missing marker, displays provenance, avoids CoinGecko, and redraws retained history', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
  assert.match(html, /\$\("scale-marker"\)\.hidden = true/);
  assert.doesNotMatch(html, /api\.coingecko\.com/);
  assert.match(html, /formatObservationTimestamp\(observedAt\)/);
  assert.match(html, /feed-errors/);
  assert.match(html, /item\.error\.message/);
  assert.match(html, /Most recent indicator reading/);
  assert.match(html, /Pipeline run time records when this file was generated/);
  assert.match(html, /item\.calculation/);
  assert.match(html, /item\.timeframe/);
  assert.match(html, /item\.sourceField/);
  assert.match(html, /item\.sourceTimestamp/);
  assert.match(html, /item\.verificationDetails/);
  assert.match(html, /item\.sourceComparison/);
  assert.match(html, /quote\.lastUpdated[^\n]*SDCAIntegrity\.formatObservationTimestamp/);
  assert.match(html, /Published source cross-check/);
  assert.match(html, /Required backlink/);
  assert.match(html, /formatObservationTimestamp/);
  assert.doesNotMatch(html, /Wilder RSI\(14\), daily BTCUSDT closes/);
  assert.match(html, /item\.substituteStatus/);
  assert.match(html, /Data fetch error/);
  assert.match(html, /JSON parsing error/);
  assert.match(html, /Data schema error/);
  assert.match(html, /Dashboard rendering error/);
  assert.match(html, /drawChart\(lastValidatedHistory\.slice\(-180\)\)/);
  assert.doesNotMatch(html, /window\.addEventListener\("resize",\s*\(\)\s*=>\s*\{\s*loadSDCAData\(\)/);
});

test('checked-in data indicator names match the dashboard and pass schema validation', () => {
  const root = path.join(__dirname, '..');
  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const block = html.match(/const INDICATORS = \[([\s\S]*?)\n    \];/);
  assert.ok(block, 'dashboard indicator list exists');
  const expected = [...block[1].matchAll(/name: "([^"]+)"/g)].map((match) => match[1]);
  const data = JSON.parse(fs.readFileSync(path.join(root, 'data/sdca-latest.json'), 'utf8'));
  assert.deepEqual(data.indicators.map((item) => item.name), expected);
  integrity.validateData(data, expected);
  integrity.validateHistory(data.history);
  const dho = data.indicators.find((item) => item.name === 'BTC Damped Harmonic Oscillator');
  assert.equal(dho.rawValue, null);
  assert.equal(dho.verificationStatus, 'unavailable');
  assert.match(dho.verificationDetails, /multiple reliable date-specific reference values/);
});


test('live BTC/USD formatting rejects invalid values and formats USD explicitly', () => {
  assert.equal(liveBTCUSD.formatUSDPrice(1234.5), '$1,234.50');
  for (const value of [0, -1, Infinity, NaN, '123']) {
    assert.throws(() => liveBTCUSD.formatUSDPrice(value), /finite positive number/);
  }
});

test('Coinbase BTC-USD ticker parser accepts documented price and time fields only when valid', () => {
  assert.deepEqual(liveBTCUSD.parseTicker({
    price: '81234.56',
    time: '2026-10-17T00:00:00.123Z'
  }), {
    price: 81234.56,
    sourceTime: '2026-10-17T00:00:00.123Z'
  });

  for (const payload of [
    null,
    [],
    {},
    { price: '0', time: '2026-10-17T00:00:00Z' },
    { price: '-10', time: '2026-10-17T00:00:00Z' },
    { price: 'not-a-price', time: '2026-10-17T00:00:00Z' },
    { price: '12.34', time: 'not-a-date' }
  ]) {
    assert.throws(() => liveBTCUSD.parseTicker(payload));
  }
});

test('live quote controller reports loading, successful USD quote, and last successful update time', async () => {
  const states = [];
  const receivedAt = new Date('2026-10-17T00:01:00.000Z');
  const controller = liveBTCUSD.createController({
    fetchImpl: async (url) => {
      assert.equal(url, liveBTCUSD.ENDPOINT);
      return {
        ok: true,
        json: async () => ({ price: '81234.56', time: '2026-10-17T00:00:59.000Z' })
      };
    },
    onState: (state) => states.push(state),
    now: () => receivedAt,
    setTimeoutImpl: () => 1,
    clearTimeoutImpl: () => {}
  });

  assert.equal(await controller.refresh(), true);
  assert.deepEqual(states.map((state) => state.status), ['loading', 'live']);
  assert.equal(states[1].price, 81234.56);
  assert.equal(states[1].sourceTime, '2026-10-17T00:00:59.000Z');
  assert.equal(states[1].receivedAt, receivedAt);
});

test('invalid JSON payload and connection errors are unavailable before first success', async () => {
  for (const fetchImpl of [
    async () => ({ ok: true, json: async () => ({ price: 'NaN', time: '2026-10-17T00:00:00Z' }) }),
    async () => { throw new Error('network offline'); }
  ]) {
    const states = [];
    const controller = liveBTCUSD.createController({
      fetchImpl,
      onState: (state) => states.push(state),
      setTimeoutImpl: () => 1,
      clearTimeoutImpl: () => {}
    });
    assert.equal(await controller.refresh(), false);
    assert.equal(states.at(-1).status, 'error');
    assert.equal(states.at(-1).price, null);
  }
});

test('failed refresh preserves the last quote and marks it stale with its successful timestamp', async () => {
  const states = [];
  let calls = 0;
  const receivedAt = new Date('2026-10-17T00:01:00.000Z');
  const controller = liveBTCUSD.createController({
    fetchImpl: async () => {
      calls += 1;
      if (calls === 1) {
        return { ok: true, json: async () => ({ price: '81234.56', time: '2026-10-17T00:00:59Z' }) };
      }
      throw new Error('connection reset');
    },
    onState: (state) => states.push(state),
    now: () => receivedAt,
    setTimeoutImpl: () => 1,
    clearTimeoutImpl: () => {}
  });

  assert.equal(await controller.refresh(), true);
  assert.equal(await controller.refresh(), false);
  const stale = states.at(-1);
  assert.equal(stale.status, 'stale');
  assert.equal(stale.price, 81234.56);
  assert.equal(stale.receivedAt, receivedAt);
  assert.match(stale.error, /connection reset/);
});

test('live quote refresh starts immediately, repeats every minute, and stops its timer', async () => {
  let calls = 0;
  let callback;
  let delay;
  let cleared = null;
  const controller = liveBTCUSD.createController({
    fetchImpl: async () => {
      calls += 1;
      return { ok: true, json: async () => ({ price: '81234.56', time: '2026-10-17T00:00:59Z' }) };
    },
    onState: () => {},
    setIntervalImpl: (fn, ms) => { callback = fn; delay = ms; return 'timer'; },
    clearIntervalImpl: (id) => { cleared = id; },
    setTimeoutImpl: () => 1,
    clearTimeoutImpl: () => {}
  });

  await controller.start();
  assert.equal(calls, 1);
  assert.equal(delay, 60_000);
  callback();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(calls, 2);
  controller.stop();
  assert.equal(cleared, 'timer');
});

test('overlapping live quote refreshes are skipped', async () => {
  let calls = 0;
  let resolveFetch;
  const controller = liveBTCUSD.createController({
    fetchImpl: () => {
      calls += 1;
      return new Promise((resolve) => { resolveFetch = resolve; });
    },
    onState: () => {},
    setTimeoutImpl: () => 1,
    clearTimeoutImpl: () => {}
  });

  const first = controller.refresh();
  assert.equal(await controller.refresh(), false);
  assert.equal(calls, 1);
  resolveFetch({ ok: true, json: async () => ({ price: '81234.56', time: '2026-10-17T00:00:59Z' }) });
  assert.equal(await first, true);
});

test('live quote request timeout is reported without throwing', async () => {
  const states = [];
  const controller = liveBTCUSD.createController({
    fetchImpl: async (_url, options) => {
      if (options.signal.aborted) throw new Error('aborted');
      return { ok: true, json: async () => ({}) };
    },
    onState: (state) => states.push(state),
    setTimeoutImpl: (callback) => { callback(); return 1; },
    clearTimeoutImpl: () => {}
  });

  assert.equal(await controller.refresh(), false);
  assert.equal(states.at(-1).status, 'error');
  assert.equal(states.at(-1).error, 'Request timed out');
});


test('dashboard keeps the live Coinbase BTC/USD quote separate from the Binance BTC/USDT daily close', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
  assert.match(html, /id="live-btc-usd-price"/);
  assert.match(html, /Coinbase Exchange/);
  assert.match(html, /BTC-USD last trade/);
  assert.match(html, /STALE · refresh failed/);
  assert.match(html, /Connection error:/);
  assert.match(html, /renderDailyClose\(data\.bitcoinPriceUSDT\)/);
  assert.match(html, /USDT is not USD/);
});
