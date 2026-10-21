# Project Handoff

## Project
- Name: JXProbability
- Repository: https://github.com/JayyTrader/JayyTrader
- Default branch: `main`
- Live site: https://jayytrader.github.io/JayyTrader/
- Operating mode: GitHub-first. No local coding. Make new work directly through the authenticated GitHub integration.

## Mandatory continuity rules
- At session start, verify GitHub access, read `AGENTS.md` and this file, and inspect the current GitHub branch/commit and target files before editing.
- If access or repository identity cannot be verified, stop and ask the operator to reconnect or clarify. Never guess.
- Make only explicitly requested changes, on a dedicated branch, and verify all resulting changes in GitHub.
- Use a pull request for changes targeting `main`. Do not merge or deploy unless the operator authorizes it.
- Never store credentials or tokens in this repository. Documentation preserves workflow, not authentication state.

## Latest verified work
- Font change PR #12: https://github.com/JayyTrader/JayyTrader/pull/12 — merged on 2026-10-21. Source Code Pro import and shared `--font-ui` token are on `main`; live rendering has not been independently verified.
- GitHub-first continuity PR #13: https://github.com/JayyTrader/JayyTrader/pull/13 — merged on 2026-10-21. `AGENTS.md` and `PROJECT_HANDOFF.md` are present on `main`.
- Text-input caret color PR #14: https://github.com/JayyTrader/JayyTrader/pull/14 — open and unmerged. Branch `ui/cyan-text-caret`; adds cyan native caret styling for inputs, textareas, and contenteditable elements. It is separate from the heading cursor below.
- Heading cursor realism PR #15: https://github.com/JayyTrader/JayyTrader/pull/15 — merged on 2026-10-21. The heading cursor now blinks sharply on/off without a glow; live browser rendering has not been independently verified.
- Brand positioning/color update PR #16: https://github.com/JayyTrader/JayyTrader/pull/16 — merged on 2026-10-21. The JxProbability wordmark is at the top-left, roughly half-size, with a hazard-yellow/amber `x`. Live rendering has not been independently verified.
- Valuation oscillator and ETH/SOL live prices in progress: branch `feature/oscillator-and-eth-sol-prices`, based on main SHA `a2923171043e7de32f1de20c323121d3cac8b0e6`. `index.html` adds a large blank −2 to +2 oscillator with +2 labeled undervalued, 0 neutral, and −2 overvalued; adds a right-side BTC/ETH/SOL price rail; and responsively stacks content on narrower screens. New `scripts/live-crypto-usd.js` fetches Coinbase Exchange ETH-USD and SOL-USD tickers independently, updates every 60 seconds, and retains last successful values as stale if refresh fails. The oscillator intentionally plots no data and has no indicators or signal calculations. Not merged or deployed; browser visual and live API testing have not been performed.
- Oscillator/price-rail alignment fix in progress: branch `fix/oscillator-price-rail-alignment-v2`, based on current main SHA `ca47dd53b61ea7e5b1c2ce2b2a0b355c0085f49e`. The desktop dashboard stretches both columns to the same grid-row height; the research column and oscillator panel fill that row; tagline/motto are positioned above the chart without consuming layout flow; responsive breakpoints restore normal stacking. The oscillator remains blank and ETH/SOL quote behavior is unchanged. Browser visual testing has not been performed.
- Next: verify the alignment-only diff, open a PR to `main`, and wait for operator authorization before merging or deploying.
