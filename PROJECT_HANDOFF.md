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
- Heading cursor realism PR in progress: branch `ui/realistic-heading-caret`, based on main SHA `5971e5781faf1b070a58fb1cda286e24a4d4265d`. In `index.html`, removes the glow and opacity-pulse effect and changes the heading cursor to a hard on/off blink at about 1.06 seconds per cycle. Not merged or deployed; browser visual testing has not been performed.
- Next: verify the heading cursor diff, open its PR, and wait for operator authorization before merging or deploying.
