const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const integrity = require('../scripts/dashboard-integrity.js');

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

test('dashboard hides missing marker, displays provenance, avoids CoinGecko, and redraws retained history', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
  assert.match(html, /\$\("scale-marker"\)\.hidden = true/);
  assert.doesNotMatch(html, /api\.coingecko\.com/);
  assert.match(html, /formatTimestamp\(item\.lastUpdated\)/);
  assert.match(html, /feed-errors/);
  assert.match(html, /item\.error\.message/);
  assert.match(html, /Most recent indicator reading/);
  assert.match(html, /Pipeline run time records when this file was generated/);
  assert.match(html, /item\.calculation/);
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
});
