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
- Valuation oscillator and ETH/SOL live prices: parent branch `feature/oscillator-and-eth-sol-prices`, based on main SHA `a2923171043e7de32f1de20c323121d3cac8b0e6`. Adds the blank −2 to +2 oscillator and BTC/ETH/SOL quote rail. Not merged or deployed; browser visual and live API testing have not been performed.
- Alignment fix in progress: branch `fix/align-oscillator-price-rail`, stacked on `feature/oscillator-and-eth-sol-prices`. The desktop dashboard grid stretches both columns to the same row height; the research column and oscillator panel fill that height, the oscillator panel has no extra top margin or fixed minimum height, and the intro sits above it without taking up layout flow. Tablet/mobile breakpoints reset to a normal stacked flow. Browser visual testing has not been performed. PR should target the parent feature branch so the alignment fix can be reviewed separately without pretending the feature is already on `main`.
- Next: verify the alignment diff and changed-file list, open the stacked PR targeting `feature/oscillator-and-eth-sol-prices`, and wait for operator authorization before merging or deploying.
