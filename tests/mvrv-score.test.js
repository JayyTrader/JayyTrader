const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const MVRVScore = require('../scripts/mvrv-score.js');

const validPayload = {
  status: 'available',
  latest: { date: '2026-10-24', rawValue: 0.85, historicalPercentile: 37, score: 0.52 }
};

test('validates normalized MVRV payload and rejects malformed values', () => {
  assert.equal(MVRVScore.validPayload(validPayload), true);
  assert.equal(MVRVScore.validPayload({ ...validPayload, latest: { ...validPayload.latest, score: 2.1 } }), false);
  assert.equal(MVRVScore.validPayload({ ...validPayload, latest: { ...validPayload.latest, historicalPercentile: 101 } }), false);
  assert.equal(MVRVScore.validPayload({ ...validPayload, status: 'unverified' }), false);
});

test('formats signed scores and checks source freshness', () => {
  assert.equal(MVRVScore.formatScore(0.52), '+0.52');
  assert.equal(MVRVScore.formatScore(-1.2), '-1.20');
  assert.equal(MVRVScore.formatRaw(0), '0.00');
  assert.equal(MVRVScore.isStale('2026-10-24', new Date('2026-10-25T12:00:00Z')), false);
  assert.equal(MVRVScore.isStale('2026-10-01', new Date('2026-10-25T12:00:00Z')), true);
  assert.equal(MVRVScore.isStale('not-a-date', new Date('2026-10-25T12:00:00Z')), true);
});

test('dashboard includes the MVRV score card and sources navigation', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
  assert.match(html, /id="mvrv-score"/);
  assert.match(html, /id="mvrv-score-value"/);
  assert.match(html, /sources\.html/);
  assert.match(html, /scripts\/mvrv-score\.js/);
});
