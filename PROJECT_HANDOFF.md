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
- Brand positioning/color update in progress: branch `ui/top-left-brand-hazard-x`, based on main SHA `e09673df41917ade9e5fa462a75e962f8df24e57`. `index.html` moves the JxProbability wordmark to the top-left, reduces its size to roughly half, and colors the `x` hazard yellow/amber. The central tagline, motto, and BTC quote remain centered. Not merged or deployed; browser visual testing has not been performed.
- Dashboard oscillator and ETH/SOL live price rail: implementation and alignment fix consolidated on branch `fix/dashboard-oscillator-alignment`, based on main SHA `a2923171043e7de32f1de20c323121d3cac8b0e6`. `index.html` positions the tagline/motto above the chart without taking layout flow; desktop grid columns stretch to the same row height; oscillator fills the row with no extra top margin or fixed minimum height; BTC/ETH/SOL rail remains stacked in that same row. Tablet/mobile layout resets to normal stacked flow. `scripts/live-crypto-usd.js` provides ETH-USD and SOL-USD Coinbase Exchange quotes, refreshed every 60 seconds. Oscillator remains blank; no indicator calculations or plots added. Browser visual verification has not been performed.
- Next: verify the consolidated branch and diff, open a PR to `main`, and wait for operator authorization before merging or deploying.
