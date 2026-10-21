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
- Font change PR #12: https://github.com/JayyTrader/JayyTrader/pull/12 — merged on 2026-10-21. The Source Code Pro font import and shared `--font-ui` token are on `main`; live rendering has not been independently verified.
- GitHub-first continuity PR #13: https://github.com/JayyTrader/JayyTrader/pull/13 — merged on 2026-10-21. `AGENTS.md` and `PROJECT_HANDOFF.md` are present on `main`.
- Text caret visibility PR #14: https://github.com/JayyTrader/JayyTrader/pull/14 — open, unmerged, and not deployed. Branch: `ui/cyan-text-caret`; head commit: `edfe02e44fb81ee4a5835451c2d7621f337f972b`. Adds a cyan `caret-color` rule for `input`, `textarea`, and `[contenteditable="true"]` in `index.html`; browser-native blinking remains intact.
- Current landing page does not contain text-entry fields, so the caret style is ready for those controls when present. No browser visual test was performed.
- Next: review PR #14, resolve any mergeability issue if needed, and wait for operator authorization before merging or deploying.
