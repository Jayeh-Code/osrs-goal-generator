# Personal Beta 1 — 2026-10-04

Live tracking and accepted-goal persistence after restart were confirmed by the owner. This release is for personal use; no external tester or Plugin Hub approval requirement.

- Failed saves show a persistent warning and Retry saving. Normal close is blocked until pending changes save successfully.
- Account lookups run one at a time, and shutdown waits asynchronously for workers.
- Refresh and polling share the same live-account guard.
- All 24 original game skill icons are bundled and verified offline.
- Diary requirements load in a background worker with explicit retry after failure.
- Cached labels distinguish the saved HiScores baseline from the last in-memory live update.
- Startup validates key nested save fields and gives backup recovery instructions without replacing damaged files.

Validation: 163 integrated desktop tests; standalone repository skips four companion-source checks. Windows executable smoke and asset checks recorded during packaging. Companion and schema unchanged; its seven tests and build passed during the readiness audit.

Limits: recovery is manual; backups may contain older progress. Abrupt termination can lose changes that could not be saved. Boss/clue progress depends on HiScores; collection unlocks require reopening the observed page. This is a beta, not a claim that every malformed save shape or every display configuration has been tested.
