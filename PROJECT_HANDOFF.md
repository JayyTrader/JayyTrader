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
- Font change PR: https://github.com/JayyTrader/JayyTrader/pull/12
- Branch: `feat/source-code-pro-font`
- Branch head: `3b6c1eb2909cf56a9813af6287a3694d3dd5458e`
- Changes: load Source Code Pro via Google Fonts in `index.html`; set the shared `--font-ui` token to Source Code Pro in `styles/tokens.css`.
- PR #12 was verified open and unmerged when this handoff was written. GitHub reported `mergeable: false`; the reason has not been diagnosed.
- Live deployment has not been verified as changed. Do not claim the font is live until the PR is merged and the deployed site is checked.

## Current documentation change
- A separate documentation-only branch `docs/github-session-continuity` was created from `main`.
- `AGENTS.md` was added in commit `72bef28a3f8126d127fd2dc2c54df7a5dd1ce3ec`.
- Next: add this handoff file, verify both files directly from GitHub, and open a documentation-only PR. Do not merge automatically.
