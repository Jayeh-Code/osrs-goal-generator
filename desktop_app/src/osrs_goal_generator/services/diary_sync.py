"""Read the isolated Ardougne prototype; never change manual completion."""
import json
from datetime import datetime, timezone
from pathlib import Path
from ..config import ASSETS_DIR

PROTOTYPE_PATH = Path.home()/'.runelite/plugin-data/osrs-diary-prototype/diary-prototype.json'


def validate(raw, rsn):
    if not isinstance(raw, dict) or type(raw.get('prototype_schema')) is not int or raw['prototype_schema'] != 1:
        return None
    if raw.get('mapping_version') != 'ardougne-tasks-1' or raw.get('status') != 'observed_unverified':
        return None
    if not isinstance(raw.get('player_name'), str) or raw['player_name'].strip().casefold() != rsn.strip().casefold():
        return None
    try:
        timestamp = datetime.fromisoformat(raw['updated_at'].replace('Z', '+00:00'))
        if timestamp.tzinfo is None:
            return None
        mapping = json.loads((ASSETS_DIR/'ardougne-task-mapping.json').read_text(encoding='utf-8'))
        tiers = raw['tiers']
        result = {}
        for tier in ('easy', 'medium', 'hard', 'elite'):
            definitions = [r for r in mapping if r['tier'] == tier]
            observed = tiers[tier]
            tasks = observed['tasks']
            expected = {f"ardougne:{tier}:{r['varp']}:{r['bit']}":r for r in definitions}
            if len(tasks) != len(expected) or {t['id'] for t in tasks} != set(expected):
                return None
            if any(type(t['bit_set']) is not bool for t in tasks):
                return None
            count = observed['count_raw']
            matches = (type(count) is int and count == sum(t['bit_set'] for t in tasks)
                       and observed.get('mapping_status') == 'count_matched_pending_journal_check')
            result[tier] = {'count': count if type(count) is int else None, 'total':len(tasks),
                           'consistent':matches, 'tasks':[{'id':t['id'], 'title':expected[t['id']]['title'],
                           'completed':t['bit_set'] if matches else None} for t in tasks]}
        return {'observed_at':raw['updated_at'], 'tiers':result}
    except (KeyError, TypeError, ValueError, OSError, AttributeError):
        return None


def load(rsn, path=PROTOTYPE_PATH):
    try:
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None, False
    result = validate(raw, rsn)
    if not result:
        return None, False
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(result['observed_at'].replace('Z','+00:00'))).total_seconds()
    return raw, -5 <= age <= 20
