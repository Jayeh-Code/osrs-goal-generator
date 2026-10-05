# OSRS Goal Generator

A personal-beta Python/PySide6 desktop command center for Old School RuneScape goals, skill progress, boss activities, paths, diaries, and observed Collection Log pages. One active goal at a time; no gameplay automation.

## Windows download and setup

Download **osrs-goal-generator-windows-x64-beta7.zip** from the [Beta 7 release](https://github.com/Jayeh-Code/osrs-goal-generator/releases/tag/v4.0.0-beta.7), extract the whole ZIP, and open **OSRS Goal Generator.exe**. Keep the `_internal` folder beside the executable. No Python installation is needed. This beta executable is unsigned.

Close the older app first. On first launch, choose **Yes** to import and select `desktop_app/user_data/state.json` from the old source download. The old save stays intact. Future downloads reuse `%LOCALAPPDATA%\OSRSGoalGenerator\user_data`, so replacing the app folder does not remove your progress. The imported original and previous readable save are backed up there. See [setup and recovery instructions](packaging/windows/START%20HERE.txt).

For source development, install Python 3.11+, download the source, run **Setup Desktop.cmd**, then **Start Desktop.cmd**. Build an executable with Python 3.13, PySide6 6.11.2, PyInstaller 6.22.0 and `python scripts/build_windows.py`.

## Live RuneLite bridge

Build and run the [RuneLite companion](https://github.com/Jayeh-Code/osrs-goal-generator-companion) using its instructions. It is not yet published to Plugin Hub. Enable it and log in, then use the same RuneScape name in the desktop app. The app reads the local plugin-data sync.json file automatically. Live skill XP takes precedence while the matching account is connected; ranks and boss/activity KC retain HiScores fallback.

Collection Log coverage grows as you open pages in game. Unopened pages are unknown. To track an unlock, choose **Track next unlock**, then **Accept** on Home. Reopen the relevant in-game Collection Log page after an unlock so the plugin can observe its exact obtained flags. Captured pages survive restart in the plugin's per-account local cache.

## Local data and privacy

Goals, history, and settings are stored in `%LOCALAPPDATA%\OSRSGoalGenerator\user_data`, independently of the application folder. Source startup copies its legacy save into this location only when no current save exists. Back up this folder regularly. No personal save data is included in this repository. Account progress stays local, except requests to public Jagex HiScores; the app can also fetch game artwork from the OSRS Wiki and public diary requirements from GitHub. There is no project server, telemetry, password handling, or Jagex login service. Never upload your user_data, bridge files, or development credentials in an issue.

The desktop remains the command center. RuneLite only observes supported game state and writes the local [schema v1](docs/SYNC_SCHEMA_V1.md) bridge.

## Tests and status

Run **Run Tests.cmd** after setup. The standalone desktop suite contains 175 tests; four legacy companion-source contract checks are skipped when the companion source is absent. The companion has its own Java regression suite. Offscreen GUI tests use temporary saves.

Validated on Windows: development companion launch, live skill XP, Collection Log page capture and restart persistence, skill goal completion, and observed collection-item goal completion. This is alpha software and is not an official Jagex or RuneLite product.

## Artwork

RuneScape names and game artwork belong to Jagex. Bundled icon provenance is retained in desktop_app/assets/catalog.json and desktop_app/assets/bosses/manifest.json. These assets are not relicensed as original project code. See THIRD_PARTY_NOTICES.md.

## Bridge status

The top status and message stay visible on every page. They explain missing or unreadable bridge data, disconnected RuneLite, stale heartbeats, and account mismatches. For an accepted collection goal, the message names the page to reopen. A matching unlock message or incomplete page prompts **WAITING FOR PAGE REFRESH**; only observed item flags verify completion. Live XP does not imply that cached collection pages are up to date. Settings shows the last bridge timestamp and cached page count.

## Reference-inspired desktop styling

Alpha 9.3 adds decorative landscape panels, stone-style borders, icon navigation and warm headings. Active goals hide disabled generation controls; smaller windows stack Home cards. Enter loads an account, Ctrl+G generates, and Alt+1 through Alt+8 switch pages. The scenery is original generated artwork; see desktop_app/assets/ui/ARTWORK.md for its prompt and provenance.

Personal beta readiness and known limits: [Beta 1 notes](docs/BETA_1.md).

Experimental all-region diary checklist requires the separate OSRS Diary Prototype development plugin. It is independent of manual diary completion and the submitted companion.
