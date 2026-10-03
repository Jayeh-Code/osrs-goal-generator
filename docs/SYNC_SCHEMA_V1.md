# Local Sync Schema v1

This schema is the contract between `runelite_companion/` and `desktop_app/`.

Representative document:

```json
{
  "schema_version": 1,
  "plugin_version": "0.1.x-alpha8",
  "updated_at": "2026-09-27T22:45:00Z",
  "connected": true,
  "game_state": "LOGGED_IN",
  "player": {
    "name": "Example RSN",
    "account_type": "unknown",
    "combat_level": 112,
    "total_level": 2031,
    "total_xp": 187654321
  },
  "skills": {
    "Agility": {"level": 82, "xp": 2673114},
    "Slayer": {"level": 93, "xp": 7240000}
  },
  "session": {
    "started_at": "2026-09-27T22:01:10Z",
    "last_event": "stat:Agility",
    "xp_gained": {"Agility": 18240}
  },
  "collection_log": {
    "pages": {
      "Vorkath": {
        "updated_at": "2026-09-27T22:44:32Z",
        "items": [
          {"item_id": 21992, "name": "Vorki", "obtained": true},
          {"item_id": 22106, "name": "Jar of decay", "obtained": false}
        ]
      }
    },
    "recent_unlocks": ["Vorki"]
  }
}
```

## Required top-level fields

- `schema_version`: integer, currently `1`.
- `plugin_version`: string.
- `updated_at`: UTC ISO-8601 timestamp string.
- `connected`: boolean.
- `game_state`: string.
- `player`: object.
- `skills`: object keyed by canonical OSRS skill name.
- `session`: object.
- `collection_log`: object.

## Player

- `name`: RSN.
- `account_type`: string; may remain `unknown` until a reliable local source exists.
- `combat_level`: integer or null.
- `total_level`: integer or null.
- `total_xp`: integer or null.

## Skills

Each skill has:

- `level`: integer >= 1.
- `xp`: integer >= 0.

Use canonical display names expected by the desktop app (for example `Attack`, `Runecraft`, `Sailing`).

## Session

Current intended fields:

- `started_at`
- `last_event`
- `xp_gained`: object keyed by skill name.

Additional session fields can be added in a backward-compatible way.

## Collection Log

`collection_log.pages` maps page names to:

- `updated_at`
- `items`: array of item objects.

Each item:

- `item_id`: integer.
- `name`: string.
- `obtained`: boolean.

`recent_unlocks` is an ordered array of recent item names when reliably observed.

## Compatibility policy

For additive fields, keep `schema_version = 1` if old readers can safely ignore them.

For breaking changes:

1. increment schema version;
2. update Java writer;
3. update Python reader;
4. update tests/fixtures;
5. document migration/fallback behavior.
