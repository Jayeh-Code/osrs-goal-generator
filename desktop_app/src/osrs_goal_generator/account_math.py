from __future__ import annotations

import math

from .models import PlayerProfile, Skill


def xp_for_level(level: int) -> int:
    if level <= 1:
        return 0
    points = 0
    for current_level in range(1, level):
        points += int(current_level + 300 * (2 ** (current_level / 7)))
    return points // 4


def xp_to_next_level(skill: Skill) -> int | None:
    if skill.level >= 99 or skill.xp < 0:
        return None
    return max(0, xp_for_level(skill.level + 1) - skill.xp)


def level_progress(skill: Skill) -> float | None:
    if skill.level >= 99 or skill.xp < 0:
        return None
    floor = xp_for_level(skill.level)
    ceiling = xp_for_level(skill.level + 1)
    if ceiling <= floor:
        return 1.0
    return max(0.0, min(1.0, (skill.xp - floor) / (ceiling - floor)))


def combat_level(profile: PlayerProfile) -> int | None:
    required = ["Attack", "Strength", "Defence", "Hitpoints", "Ranged", "Prayer", "Magic"]
    if any(profile.skill(name) is None for name in required):
        return None

    attack = profile.skill("Attack").level
    strength = profile.skill("Strength").level
    defence = profile.skill("Defence").level
    hitpoints = profile.skill("Hitpoints").level
    ranged = profile.skill("Ranged").level
    prayer = profile.skill("Prayer").level
    magic = profile.skill("Magic").level

    base = 0.25 * (defence + hitpoints + math.floor(prayer / 2))
    melee = 0.325 * (attack + strength)
    ranged_style = 0.325 * math.floor(ranged * 1.5)
    magic_style = 0.325 * math.floor(magic * 1.5)
    return math.floor(base + max(melee, ranged_style, magic_style))


def trainable_skills(profile: PlayerProfile) -> list[Skill]:
    return [
        skill
        for name, skill in profile.skills.items()
        if name != "Overall" and 1 <= skill.level < 99
    ]


def lowest_skills(profile: PlayerProfile, count: int = 5) -> list[Skill]:
    return sorted(trainable_skills(profile), key=lambda s: (s.level, s.xp, s.name))[:count]
