const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
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
  assert.equal(integrity.compositeMarkerPercent(2), 0);
  assert.equal(integrity.compositeMarkerPercent(-2), 100);
  assert.equal(integrity.validateCompositeScore(2), 2);
  assert.equal(integrity.validateCompositeScore(-2), -2);
});

test('composite values outside fixed oscillator range and malformed history scores are rejected', () => {
  for (const value of [-2.001, 2.001, Infinity, NaN]) {
    assert.throws(() => integrity.compositeMarkerPercent(value), /finite number/);
  }
  assert.equal(integrity.validateScore(3, 'indicator score'), 3, 'legacy indicator score validation remains unchanged');
  assert.throws(() => integrity.validateHistory([{ date: '2025-01-01', score: 3.1 }]), /finite number/);
});

test('verified composite requires explicit scoring approval, all 15 verified inputs, and a matching dated observation', () => {
  const data = baseData();
  data.indicators = names.map((name) => ({ name, category: 'Test', score: 0, status: 'valid' }));
  data.compositeScore = 0.5;
  data.dataIntegrity = { scoringRulesApproved: true, compositeCalculated: true, verifiedScores: 15 };
  const historyState = { history: [{ date: '2026-10-15', score: 0.5 }], error: null };

  const approved = integrity.verifiedCompositeObservation(data, historyState);
  assert.deepEqual(approved, { available: true, score: 0.5, date: '2026-10-15', reason: null });

  const noApproval = structuredClone(data);
  noApproval.dataIntegrity.scoringRulesApproved = false;
  assert.match(integrity.verifiedCompositeObservation(noApproval, historyState).reason, /approved SDCA scoring rules/);

  const partialInputs = structuredClone(data);
  partialInputs.indicators[14].status = 'unverified';
  assert.match(integrity.verifiedCompositeObservation(partialInputs, historyState).reason, /all 15 indicator scores/);

  const uncalculated = structuredClone(data);
  uncalculated.dataIntegrity.compositeCalculated = false;
  assert.match(integrity.verifiedCompositeObservation(uncalculated, historyState).reason, /all 15 indicator scores/);

  const noDate = integrity.verifiedCompositeObservation(data, { history: [], error: null });
  assert.match(noDate.reason, /no validated, dated composite observation/);

  const invalidDate = integrity.verifiedCompositeObservation(data, { history: [{ date: '2026-02-30', score: 0.5 }], error: null });
  assert.match(invalidDate.reason, /history failed validation/);

  const mismatch = integrity.verifiedCompositeObservation(data, { history: [{ date: '2026-10-15', score: 0.4 }], error: null });
  assert.match(mismatch.reason, /does not match/);

  const outOfRange = { ...data, compositeScore: 2.01 };
  assert.match(integrity.verifiedCompositeObservation(outOfRange, historyState).reason, /-2 to \+2/);
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
  assert.match(html, /SDCAIntegrity\.formatObservationTimestamp\(observedAt,\s*formatTimestamp\)/);
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

test('actual dashboard indicator renderers format source dates through the shared helper', () => {
  const root = path.join(__dirname, '..');
  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
  const inlineScript = scripts.find((script) => script.includes('function renderIndicatorCards(indicators)'));
  assert.ok(inlineScript, 'dashboard inline renderer script exists');

  const start = inlineScript.indexOf('    function renderIndicatorCards(indicators) {');
  const end = inlineScript.indexOf('    function renderSourceLinks(item, table = false) {', start);
  assert.ok(start >= 0 && end > start, 'actual card and table renderer definitions are available');
  const rendererSource = inlineScript.slice(start, end);
  const rendered = new Map();
  const context = {
    SDCAIntegrity: integrity,
    formatTimestamp: (value) => `formatted:${value}`,
    formatScore: (value) => Number(value).toFixed(2),
    escapeHTML: (value) => String(value).replace(/[&<>\"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '\"': '&quot;', "'": '&#39;'
    })[char]),
    renderSourceLinks: () => 'Source link',
    $: (id) => {
      if (!rendered.has(id)) rendered.set(id, { innerHTML: '' });
      return rendered.get(id);
    }
  };
  vm.runInNewContext(`${rendererSource}
this.renderIndicatorCards = renderIndicatorCards;
this.renderIndicatorTable = renderIndicatorTable;`, context);

  const data = JSON.parse(fs.readFileSync(path.join(root, 'data/sdca-latest.json'), 'utf8'));
  integrity.validateData(data, data.indicators.map((item) => item.name));
  assert.doesNotThrow(() => context.renderIndicatorCards(data.indicators));
  assert.doesNotThrow(() => context.renderIndicatorTable(data.indicators));
  assert.match(rendered.get('indicator-grid').innerHTML, /Source observation: 2026-10-15 \(UTC source date\)/);
  assert.match(rendered.get('indicator-table').innerHTML, /Source observation: 2026-10-15 \(UTC source date\)/);
});

test('Coinbase Exchange link styling is scoped and covers visited, hover, and keyboard focus states', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
  const style = html.match(/<style>([\s\S]*?)<\/style>/);
  assert.ok(style, 'dashboard stylesheet exists');
  assert.match(html, /class=\"live-btc-usd-link\" href=\"https:\/\/docs\.cdp\.coinbase\.com\//);
  assert.match(style[1], /\.live-btc-usd-link:link,\s*\.live-btc-usd-link:visited\s*\{[^}]*color:\s*var\(--muted\)/);
  assert.match(style[1], /\.live-btc-usd-link:hover,\s*\.live-btc-usd-link:focus-visible\s*\{[^}]*color:\s*var\(--mint\)/);
  assert.match(style[1], /\.live-btc-usd-link:focus-visible\s*\{[^}]*outline:\s*1px solid var\(--green\)/);
  assert.doesNotMatch(style[1], /(?:^|[,\s])a:(?:link|visited|hover|focus-visible)/);
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

test('homepage uses the fixed-range composite oscillator and removes the BTC market chart feature', () => {
  const root = path.join(__dirname, '..');
  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const data = JSON.parse(fs.readFileSync(path.join(root, 'data/sdca-latest.json'), 'utf8'));
  assert.match(html, /<h2>SDCA Composite Oscillator<\/h2>/);
  assert.match(html, /Fixed score range from −2\.0 to \+2\.0/);
  assert.match(html, /−2 · OVERVALUED/);
  assert.match(html, /0 · NEUTRAL/);
  assert.match(html, /\+2 · UNDERVALUED/);
  assert.match(html, /id="chart-latest-time"/);
  assert.match(html, /scoringRulesApproved/);
  assert.match(html, /History outside fixed −2 to \+2 range; no values were rescaled/);
  assert.doesNotMatch(html, /Bitcoin \/ USD Market Chart|TradingView Lightweight Charts|btc-usd-chart|lightweight-charts/);
  assert.doesNotMatch(html, /scripts\/btc-usd-chart\.js/);
  assert.equal(fs.existsSync(path.join(root, 'scripts/btc-usd-chart.js')), false);

  assert.equal(data.dataIntegrity.compositeCalculated, false);
  assert.equal(data.dataIntegrity.verifiedScores, 0);
  assert.equal(data.compositeScore, null);
  assert.deepEqual(data.history, []);
  assert.match(html, /Unavailable · approved SDCA scoring rules are not configured/);
});

test('actual oscillator renderer draws only the −2, 0, +2 scale and does not rescale legacy history', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
  const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
  const inlineScript = scripts.find((script) => script.includes('function drawChart(history)'));
  assert.ok(inlineScript, 'actual oscillator renderer exists');
  const start = inlineScript.indexOf('    function drawChart(history) {');
  const end = inlineScript.indexOf('    let lastValidatedHistory = [];', start);
  assert.ok(start >= 0 && end > start, 'actual drawChart function is available');
  const rendererSource = inlineScript.slice(start, end);
  const labels = [];
  let strokeCount = 0;
  const ctx = {
    setTransform() {}, clearRect() {}, beginPath() {}, setLineDash() {}, moveTo() {}, lineTo() {},
    stroke() { strokeCount += 1; }, fillText(value) { labels.push(value); }, fill() {}, closePath() {}
  };
  const canvas = { width: 0, height: 0, getContext: () => ctx, getBoundingClientRect: () => ({ width: 400, height: 300 }) };
  const context = {
    SDCAIntegrity: integrity,
    window: { devicePixelRatio: 1 },
    $: (id) => id === 'sdca-chart' ? canvas : null
  };
  vm.runInNewContext(`${rendererSource}\nthis.drawChart = drawChart;`, context);

  context.drawChart([]);
  assert.deepEqual(labels.slice(0, 3), ['+2', '0', '-2']);
  assert.match(labels.at(-1), /Historical data will appear/);

  labels.length = 0;
  strokeCount = 0;
  context.drawChart([{ date: '2026-10-15', score: 3 }]);
  assert.equal(labels.at(-1), 'History outside fixed −2 to +2 range; no values were rescaled');
  assert.equal(strokeCount, 3, 'only the three reference grid lines are drawn for out-of-range history');
});

test('composite observation renderer keeps missing values unavailable and displays date-only UTC source dates', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
  const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
  const inlineScript = scripts.find((script) => script.includes('function setComposite(observation)'));
  assert.ok(inlineScript, 'actual composite display renderer exists');
  const start = inlineScript.indexOf('    function setComposite(observation) {');
  const end = inlineScript.indexOf('    function drawChart(history) {', start);
  const rendererSource = inlineScript.slice(start, end);
  const elements = new Map();
  const context = {
    SDCAIntegrity: integrity,
    formatScore: (value) => `${value > 0 ? '+' : ''}${Number(value).toFixed(2)}`,
    formatTimestamp: (value) => `timestamp:${value}`,
    $: (id) => {
      if (!elements.has(id)) elements.set(id, { textContent: '', className: '', hidden: true, style: {} });
      return elements.get(id);
    }
  };
  vm.runInNewContext(`${rendererSource}\nthis.setComposite = setComposite;`, context);

  context.setComposite({ available: false, reason: 'Unavailable · approved SDCA scoring rules are not configured.' });
  assert.equal(elements.get('composite-score').textContent, '—');
  assert.equal(elements.get('scale-marker').hidden, true);
  assert.equal(elements.get('chart-latest-time').textContent, 'UTC observation: unavailable');

  context.setComposite({ available: true, score: 1.25, date: '2026-10-15' });
  assert.equal(elements.get('chart-latest').textContent, '+1.25');
  assert.equal(elements.get('chart-latest-time').textContent, 'UTC observation: 2026-10-15 (UTC source date)');
  assert.equal(elements.get('scale-marker').style.left, '18.75%');
});

test('live Coinbase USD quote remains separate from retained Binance USDT daily-close data', () => {
  const root = path.join(__dirname, '..');
  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const data = JSON.parse(fs.readFileSync(path.join(root, 'data/sdca-latest.json'), 'utf8'));
  assert.match(html, /Live Bitcoin \/ USD/);
  assert.match(html, /Coinbase Exchange/);
  assert.match(html, /BTC-USD last trade/);
  assert.doesNotMatch(html, /Bitcoin \/ USD Market Chart/);
  assert.equal(data.bitcoinPriceUSDT.quoteCurrency, 'USDT');
  assert.equal(data.bitcoinPriceUSDT.lastUpdated, '2026-10-16');
  assert.match(fs.readFileSync(path.join(root, 'scripts/update_sdca.py'), 'utf8'), /bitcoinPriceUSDT/);
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

test('stopping during an active live quote request clears its interval and aborts safely', async () => {
  const states = [];
  let intervalCallback;
  let intervalId;
  const clearedIntervals = [];
  let requestSignal;
  let abortEvents = 0;
  const controller = liveBTCUSD.createController({
    fetchImpl: (_url, options) => new Promise((_resolve, reject) => {
      requestSignal = options.signal;
      options.signal.addEventListener('abort', () => {
        abortEvents += 1;
        const error = new Error('request aborted');
        error.name = 'AbortError';
        reject(error);
      }, { once: true });
    }),
    onState: (state) => states.push(state),
    setIntervalImpl: (callback) => {
      intervalCallback = callback;
      intervalId = { timer: 'quote-refresh' };
      return intervalId;
    },
    clearIntervalImpl: (id) => clearedIntervals.push(id),
    setTimeoutImpl: () => 'request-timeout',
    clearTimeoutImpl: () => {}
  });

  const initialRequest = controller.start();
  assert.equal(states.at(-1).status, 'loading');
  assert.equal(typeof intervalCallback, 'function');
  assert.equal(requestSignal.aborted, false);

  assert.doesNotThrow(() => controller.stop());
  assert.doesNotThrow(() => controller.stop());
  let watchdog;
  const result = await Promise.race([
    initialRequest,
    new Promise((resolve) => { watchdog = setTimeout(() => resolve('still-pending'), 100); })
  ]);
  clearTimeout(watchdog);

  assert.notEqual(result, 'still-pending', 'start should settle after stop aborts its active request');
  assert.equal(result, false);
  assert.equal(requestSignal.aborted, true);
  assert.equal(abortEvents, 1);
  assert.deepEqual(clearedIntervals, [intervalId]);
  assert.equal(states.at(-1).status, 'error');
  assert.equal(states.at(-1).price, null);
  assert.equal(['loading', 'refreshing'].includes(states.at(-1).status), false);
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

test('a pending live quote request is aborted at the 10-second timeout and leaves loading state', async () => {
  const states = [];
  let requestSignal;
  let timeoutCallback;
  let timeoutDelay;
  let clearedTimeout = null;
  const controller = liveBTCUSD.createController({
    fetchImpl: (_url, options) => new Promise((_resolve, reject) => {
      requestSignal = options.signal;
      options.signal.addEventListener('abort', () => {
        const error = new Error('request aborted');
        error.name = 'AbortError';
        reject(error);
      }, { once: true });
    }),
    onState: (state) => states.push(state),
    setTimeoutImpl: (callback, delay) => {
      timeoutCallback = callback;
      timeoutDelay = delay;
      return 'request-timeout';
    },
    clearTimeoutImpl: (id) => { clearedTimeout = id; }
  });

  const refresh = controller.refresh();
  assert.equal(states.at(-1).status, 'loading');
  assert.equal(timeoutDelay, 10_000);
  assert.equal(requestSignal.aborted, false);

  timeoutCallback();
  let watchdog;
  const result = await Promise.race([
    refresh,
    new Promise((resolve) => { watchdog = setTimeout(() => resolve('still-pending'), 100); })
  ]);
  clearTimeout(watchdog);

  assert.notEqual(result, 'still-pending', 'refresh should settle when its request is aborted');
  assert.equal(result, false);
  assert.equal(requestSignal.aborted, true);
  assert.equal(clearedTimeout, 'request-timeout');
  assert.equal(states.at(-1).status, 'error');
  assert.equal(states.at(-1).price, null);
  assert.equal(states.at(-1).error, 'Request timed out');
  assert.equal(['loading', 'refreshing'].includes(states.at(-1).status), false);
});


test('homepage shows one USD BTC price card and retains Binance daily-close data collection', () => {
  const root = path.join(__dirname, '..');
  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const overview = html.match(/<section class="grid overview-grid"[^>]*>([\s\S]*?)<\/section>/);
  assert.ok(overview, 'homepage overview grid exists');
  const cards = [...overview[1].matchAll(/<article class="panel">([\s\S]*?)<\/article>/g)].map((match) => match[1]);
  const btcPriceCards = cards.filter((card) => /class="big-number price"/.test(card));
  assert.equal(btcPriceCards.length, 1, 'only one BTC price card is visible in the overview');
  assert.match(btcPriceCards[0], /<div class="panel-label">Live Bitcoin \/ USD<\/div>/);
  assert.match(btcPriceCards[0], /id="live-btc-usd-price"/);
  assert.doesNotMatch(overview[1], /Bitcoin \/ USDT|id="btc-price"|id="btc-updated"/);
  assert.match(btcPriceCards[0], /Coinbase Exchange/);
  assert.match(btcPriceCards[0], /Last successful update/);
  assert.match(btcPriceCards[0], /refreshes about every 60 seconds/);
  assert.match(btcPriceCards[0], /live-quote-status/);

  const data = JSON.parse(fs.readFileSync(path.join(root, 'data/sdca-latest.json'), 'utf8'));
  assert.equal(data.bitcoinPriceUSDT.quoteCurrency, 'USDT');
  const pipeline = fs.readFileSync(path.join(root, 'scripts/update_sdca.py'), 'utf8');
  assert.match(pipeline, /"bitcoinPriceUSDT": btc_price/);
});
