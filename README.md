# OSRS Goal Generator

An alpha Python/PySide6 desktop command center for Old School RuneScape goals, skill progress, boss activities, paths, diaries, and observed Collection Log pages. One active goal at a time; no gameplay automation.

## Windows download and setup

1. Install Python 3.11 or newer from https://www.python.org/downloads/windows/ (include the Python launcher).
2. Choose **Code > Download ZIP** on this repository, then extract the ZIP to a writable folder such as Documents.
3. Double-click **Setup Desktop.cmd** once to install PySide6 into a local virtual environment. This step needs internet access.
4. Double-click **Start Desktop.cmd** to open the app.
5. Load your RuneScape name. Public HiScores works without the RuneLite companion.

Keep the extracted folder together. This is a source distribution, not a standalone EXE or installer.

## Live RuneLite bridge

Build and run the [RuneLite companion](https://github.com/Jayeh-Code/osrs-goal-generator-companion) using its instructions. It is not yet published to Plugin Hub. Enable it and log in, then use the same RuneScape name in the desktop app. The app reads the local plugin-data sync.json file automatically. Live skill XP takes precedence while the matching account is connected; ranks and boss/activity KC retain HiScores fallback.

Collection Log coverage grows as you open pages in game. Unopened pages are unknown. To track an unlock, choose **Track next unlock**, then **Accept** on Home. Reopen the relevant in-game Collection Log page after an unlock so the plugin can observe its exact obtained flags. Captured pages survive restart in the plugin's per-account local cache.

## Local data and privacy

Goals, history, and settings are stored in desktop_app/user_data inside your extracted folder. Back up that folder before replacing a download. No personal save data is included in this repository. Account progress stays local, except requests to public Jagex HiScores; the app can also fetch game artwork from the OSRS Wiki. There is no project server, telemetry, password handling, or Jagex login service. Never upload your user_data, bridge files, or development credentials in an issue.

The desktop remains the command center. RuneLite only observes supported game state and writes the local [schema v1](docs/SYNC_SCHEMA_V1.md) bridge.

## Tests and status

Run **Run Tests.cmd** after setup. The standalone desktop suite contains 136 tests; four legacy companion-source contract checks are skipped when the companion source is absent. The companion has its own Java regression suite. Offscreen GUI tests use temporary saves.

Validated on Windows: development companion launch, live skill XP, Collection Log page capture and restart persistence, skill goal completion, and observed collection-item goal completion. This is alpha software and is not an official Jagex or RuneLite product.

## Artwork

RuneScape names and game artwork belong to Jagex. Bundled icon provenance is retained in desktop_app/assets/catalog.json and desktop_app/assets/bosses/manifest.json. These assets are not relicensed as original project code. See THIRD_PARTY_NOTICES.md.
