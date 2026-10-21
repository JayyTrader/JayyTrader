# GitHub-First Coding Protocol

## Mission
Build JXProbability forward in the existing repository. Do not import unrelated local code or perform local coding.

## Single source repository
- Repository: https://github.com/JayyTrader/JayyTrader
- Default branch: `main`
- Live site: https://jayytrader.github.io/JayyTrader/
- Make implementation changes through the authenticated GitHub integration whenever it is available.
- Never create a second repository for this project.

## Mandatory start-of-session verification
1. Verify that the connected GitHub integration can access `JayyTrader/JayyTrader`.
2. Read this file and `PROJECT_HANDOFF.md`.
3. Verify the target branch and current commit from GitHub before editing.
4. Fetch/read the exact current contents and blob SHA of every file to be changed.
5. Confirm the requested scope with the operator when it is ambiguous.
6. If repository identity, access, branch, or file state cannot be verified, stop. Do not guess, use an unverified remote, or claim connectivity is ready.

## Change protocol
1. Use a dedicated branch for each coherent change.
2. Make only the explicitly requested changes. Do not introduce unrelated refactors, dependencies, visual changes, or feature work.
3. Apply changes directly through the GitHub integration, not a local checkout.
4. Verify the resulting file contents, commit SHA, changed-file list, and pull request state from GitHub.
5. Prefer a pull request to `main`; do not merge or publish to the live site unless explicitly authorized.
6. Never force-push, reset, rebase, rewrite history, change repository identity, or overwrite unrelated work without explicit authorization.
7. Report what was actually verified. A successful GitHub API operation does not by itself prove the deployed website works or that authentication will persist indefinitely.

## Session end
Update `PROJECT_HANDOFF.md` through GitHub when meaningful work changes the verified state. Record the current branch, commit/PR, exact files changed, what remains unverified, and the next safe action. Never mark work complete unless confirmed.

## Connection limitations
This document preserves the workflow, not credentials or an authenticated session. GitHub authorization can expire or be disconnected. At each session start, verify access anew. If access fails, ask the operator to reconnect the GitHub integration; never request or store passwords, personal access tokens, or other secrets in repository files.
