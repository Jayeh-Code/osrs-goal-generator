# Personal beta readiness audit

2026-10-04 — desktop Alpha 9.3 and current companion source.

## Reliability patch update

Packaged verification completed: Alpha 9.4 launched without Python on PATH, exited successfully, reported eight screens and 71 readable boss icons, and its Windows screenshot was inspected. Local ZIP and SHA-256 file are in the parent output folder. The remaining user check is accepted-goal restart and RuneLite logout/reconnect with this build. No GitHub release was published in this pass.

B1-B3 are addressed in Alpha 9.4. All 160 desktop tests pass, including simulated failed acceptance/progress/completion/preference saves, retry without duplicate history, blocked close on unsaved data, a delayed real worker with repeated lookup and shutdown, and rejected non-logged-in refresh. Pending changes remain in memory with a persistent warning and Retry saving; a failed save prevents normal close. Abrupt process termination or power loss can still lose unsaved changes. The companion and schema are unchanged. A packaged check and user restart/reconnect check follow; the original audit below is retained as evidence.

## Verdict and scope

Close to personal beta. Complete a focused reliability pass before changing the version label. This product is for Jay's own use: Plugin Hub approval, other testers, an installer, signing, public onboarding, and new features are not beta gates. The working development client is acceptable.

This audit changed documentation only. No release, PR change, personal-save access, or credential access was performed.

## Verification

- Fresh desktop run: 155 tests passed and Python compilation checks passed, using an isolated save directory.
- Fresh companion build with `--rerun-tasks`: successful compilation and seven Java lifecycle tests, zero failures/errors/skips. An unchecked-operation note in the developer launcher is not a build failure.
- Two synthetic GUI probes reproduced B1 and B3 below. They demonstrate defects, not corrected behavior.
- Prior user-confirmed evidence: live XP, skill completion, collection page capture/cache restart, accepted collection completion after page refresh, filters, standalone upgrades, and approved Alpha 9.3 appearance.
- Prior executable smoke: eight screens, 71 readable boss icons. Not repeated for this documentation-only audit.
- Existing tests cover stale/wrong-account bridges, goal checkpoints, duplicate completion, imports/backups, filters, progression and compact Home layout. Some older tests inspect source text; 155 tests does not mean 155 end-to-end scenarios.

## Findings

### B1: Save failure leaves memory ahead of disk — fix before beta

`MainWindow._poll_runelite_sync` updates/archives a completed goal before calling `StateStore.save`. A simulated PermissionError escaped the callback, leaving no active goal in memory while the saved file retained the accepted goal. Other UI actions also save directly without a shared recovery path. Atomic writes protect the previous file; the missing behavior is communicating and recovering unsaved changes.

Acceptance: persistent actionable save-failure notice; reliable retry or rollback; no implication that unsaved changes are durable. Cover acceptance, partial progress, completion and preferences with synthetic failures and a successful retry.

### B2: Account lookup overlap and shutdown — fix before beta

Source finding, not a reproduced live crash: Return calls `_load_account`, which disables buttons but has no in-flight guard. Repeated Enter can start additional workers and replace stored thread/worker references. MainWindow has no closeEvent handling for the running fetch thread.

Acceptance: one lookup at a time, harmless repeated Enter, safe close during a delayed request, and no old response replacing a later selected account. Use a controlled delayed client.

### B3: Inconsistent live-data guard on refresh — fix in the same pass

Reproduced: `_profile_loaded` checks freshness and matching RSN but not LOGGED_IN before merging skills. A fresh connected LOGIN_SCREEN fixture overlaid XP while the ordinary live-status/progress helper rejected it. This is a defensive consistency gap; it does not establish that the current companion normally emits this combination.

Acceptance: refresh and polling share the connected/fresh/matching/logged-in guard. Rejected snapshots cannot overlay skills.

### B4: Hardening before personal 1.0

- Save import/startup checks outer structure, but nested preferences/counts are assumed valid downstream. Malformed nested data may fail later without useful recovery guidance. Syntactically corrupt saves are already refused and backups retained.
- Uncached diary requirements load synchronously from GUI code with a 12-second network timeout; this can temporarily freeze the interface. Cached requirements avoid the normal request.
- Live profile XP is merged in memory, while profile snapshots are saved on account refresh. Active skill-goal checkpoints persist separately. Restarting without RuneLite can display an older profile alongside newer saved goal progress. Consider periodic live-profile persistence or explicit cached-snapshot age; avoid flooding the 30-snapshot analytics history.

## Feature assessment

| Area | Evidence and accepted limits |
| --- | --- |
| Skill goals | User confirmed live completion; checkpoint/fallback tests pass. |
| Collection goals | Exact observed IDs and accepted-task completion verified. Reopen the page after an unlock; unseen pages stay unknown. |
| Boss/clue goals | Progress tests pass; use HiScores refresh, not live kill tracking. A real accepted completion remains useful final-release evidence. |
| Paths | Persistence and progression tests pass. |
| Diaries | Readiness and manual completion supported; quests intentionally assumed complete; tasks not automatically verified. |
| Manual collections | Explicit manual data, separate from observed RuneLite pages. |
| Stats/history | Existing coverage; retained history is bounded to 30 profile snapshots and 100 goals, not a lifetime journal. |
| UI | User approved; Home tested at 1100x760 and 1440x900. Every screen/scaling level has not been visually audited. |
| Saves/upgrades | Stable directory, preserved import, rolling backup and application lock tested. B1 remains a gap. |

Unranked boss counts are treated as zero for baselines; this cannot establish exact below-ranking-threshold KC. Local bridge does not mean every data source is offline: HiScores, optional asset downloads and diary requirements use public sources.

## Exit criteria

Personal beta: fix B1–B3 with behavioral tests, rerun relevant suites, package and smoke-test the executable, then verify an accepted goal survives desktop restart and RuneLite logout/reconnect. Prior game tests count; no need to recapture every page or obtain another rare drop.

Personal 1.0: address B4 where relevant to daily use and finish several normal play sessions without lost state, wrong-account updates or false completion. Check boss/clue completion if those workflows matter to Jay. No external testers or Plugin Hub dependency required. New features can follow later.

Next work: a focused reliability patch for B1–B3, preserving the approved GUI, existing schema and sensor-only architecture.
