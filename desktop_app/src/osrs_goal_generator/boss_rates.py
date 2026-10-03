from __future__ import annotations

from dataclasses import dataclass
import math


INTENSITY_MULTIPLIERS = {
    "chill": 0.65,
    "moderate": 1.00,
    "grind": 1.35,
}


@dataclass(frozen=True, slots=True)
class BossRate:
    """Sustainable completion-rate estimate for a late-mid-game account.

    `benchmark_rate` is a current guide/community benchmark used as an upper
    sanity cap. `late_mid_rate` is deliberately more conservative and is what
    the app uses for Moderate goals.
    """

    name: str
    late_mid_rate: float | None
    benchmark_rate: float | None
    unit: str = "KC"
    minimum_session_minutes: int = 15
    targetable: bool = True
    confidence: str = "medium"
    source_group: str = "guide benchmark"
    note: str = ""

    def effective_rate(self, difficulty: str) -> float | None:
        if self.late_mid_rate is None or not self.targetable:
            return None
        multiplier = INTENSITY_MULTIPLIERS.get(difficulty, 1.0)
        rate = self.late_mid_rate * multiplier
        if self.benchmark_rate and self.benchmark_rate > 0:
            # Grind can push a late-mid player, but should not silently demand
            # more than the current guide benchmark used to calibrate the boss.
            rate = min(rate, self.benchmark_rate)
        return max(0.0, rate)

    def target_increment(self, session_minutes: int, difficulty: str) -> int | None:
        if not self.targetable or session_minutes < self.minimum_session_minutes:
            return None
        rate = self.effective_rate(difficulty)
        if rate is None:
            return None
        expected = rate * (session_minutes / 60.0)
        # Floor instead of round: a goal should be sustainable, not require the
        # player to beat the calibrated pace because of a .5 rounding artifact.
        return max(1, math.floor(expected + 1e-9))


# Research basis, reviewed 27 Sep 2026:
# - OSRS Wiki-derived money-making benchmarks surfaced through OSRS Methods,
#   OSRS Index, ScapePath and current 2026 boss guides.
# - OnDropRate average-gear rates for several newer / Wilderness bosses.
# - TempleOSRS EHB rates only as an upper-bound sanity check, not as the goal rate.
#
# These are NOT max-efficiency rates. Moderate is intended to be a sustainable
# late-mid-game target. Chill = ~65% of that pace. Grind = up to 135%, capped at
# the current guide benchmark when one is available.
BOSS_RATES: dict[str, BossRate] = {
    "Abyssal Sire": BossRate("Abyssal Sire", 28, 39, note="Experienced guide benchmark ~39/h."),
    "Alchemical Hydra": BossRate("Alchemical Hydra", 20, 25, note="Wiki-derived guides commonly use ~22-25/h."),
    "Amoxliatl": BossRate("Amoxliatl", 30, 40),
    "Araxxor": BossRate("Araxxor", 28, 39, note="Wiki-derived money guide benchmark ~39/h."),
    "Artio": BossRate("Artio", 35, 47, source_group="average-gear drop-rate model"),
    "Barrows Chests": BossRate("Barrows Chests", 8, 12, unit="chests"),
    "Brutus": BossRate("Brutus", 45, 60, source_group="average-gear drop-rate model", note="Very fast respawn boss; EHB ceiling is much higher."),
    "Bryophyta": BossRate("Bryophyta", 18, 25, note="Key-gated; rate assumes keys are already banked."),
    "Callisto": BossRate("Callisto", 16, 25, source_group="wiki-derived money guide", note="Wilderness interruptions can lower real rate."),
    "Calvar'ion": BossRate("Calvar'ion", 38, 51, source_group="average-gear drop-rate model", note="Wilderness interruptions can lower real rate."),
    "Cerberus": BossRate("Cerberus", 35, 50, note="Current guide benchmark ~50/h with max melee/Emberlight; late-mid rate is lower."),
    "Chambers of Xeric": BossRate("Chambers of Xeric", 1.5, 3.0, unit="raids", minimum_session_minutes=30, note="Late-mid team/learning pace; experienced teams can be much faster."),
    "Chambers of Xeric: Challenge Mode": BossRate("Chambers of Xeric: Challenge Mode", 1.0, 1.7, unit="raids", minimum_session_minutes=45, note="Experienced solo benchmark ~1.7/h."),
    "Chaos Elemental": BossRate("Chaos Elemental", 35, 60, note="Wilderness interruptions can lower real rate."),
    "Chaos Fanatic": BossRate("Chaos Fanatic", 35, 60, note="Wilderness interruptions can lower real rate."),
    "Commander Zilyana": BossRate("Commander Zilyana", 15, 27, note="Conservative late-mid solo/small-team pace."),
    "Corporeal Beast": BossRate("Corporeal Beast", 5, 10, note="Assumes a small team or practical non-max setup."),
    "Crazy Archaeologist": BossRate("Crazy Archaeologist", 20, 27, source_group="wiki-derived money guide"),
    "Dagannoth Prime": BossRate("Dagannoth Prime", 18, 40, note="Per-king estimate; benchmark usually reports combined DK throughput."),
    "Dagannoth Rex": BossRate("Dagannoth Rex", 18, 40, note="Per-king estimate; benchmark usually reports combined DK throughput."),
    "Dagannoth Supreme": BossRate("Dagannoth Supreme", 18, 40, note="Per-king estimate; benchmark usually reports combined DK throughput."),
    "Deranged Archaeologist": BossRate("Deranged Archaeologist", 30, 45),
    "Doom of Mokhaiotl": BossRate("Doom of Mokhaiotl", 2.5, 2.8, unit="runs", minimum_session_minutes=30, source_group="average-gear delve model", note="Rate models a full mid-depth delve run, not an individual floor."),
    "Duke Sucellus": BossRate("Duke Sucellus", 22, 34, note="Experienced guide benchmark ~34/h; late-mid rate leaves prep/mistake margin."),
    "General Graardor": BossRate("General Graardor", 15, 27, note="Conservative late-mid solo/small-team pace."),
    "Giant Mole": BossRate("Giant Mole", 50, 85, note="Older accessible setups are around 50/h; current Tbow benchmark is ~85/h."),
    "Grotesque Guardians": BossRate("Grotesque Guardians", 18, 24, note="Current wiki-derived guide benchmark ~24/h."),
    "Hespori": BossRate("Hespori", 1, 1, unit="kills", minimum_session_minutes=15, note="Farming-growth gated; target is one available kill."),
    "Kalphite Queen": BossRate("Kalphite Queen", 16, 22, note="Current guide assumption ~22/h; up to ~34/h with max gear/stats."),
    "King Black Dragon": BossRate("King Black Dragon", 20, 65, note="Recent mid-game guidance places budget setups around 15-20/h; dragon-hunter setups can be much faster."),
    "Kraken": BossRate("Kraken", 50, 60, note="Wiki-derived guide benchmark ~60/h; highly AFK."),
    "Kree'Arra": BossRate("Kree'Arra", 14, 27, note="Conservative late-mid solo/small-team pace."),
    "K'ril Tsutsaroth": BossRate("K'ril Tsutsaroth", 14, 26, note="Conservative late-mid solo/small-team pace."),
    "Lunar Chests": BossRate("Lunar Chests", 7, 10, unit="chests", note="Perilous Moons chest completions."),
    "Mad Angel": BossRate("Mad Angel", 28, 39, source_group="average-gear drop-rate model"),
    "Maggot King": BossRate("Maggot King", 17, 24, source_group="average-gear drop-rate model"),
    "Mimic": BossRate("Mimic", None, None, targetable=False, source_group="special access", note="Clue-casket encounter; cannot be farmed on demand."),
    "Nex": BossRate("Nex", 6, 10, note="Small-team late-mid contribution/completion pace."),
    "Nightmare": BossRate("Nightmare", 6, 12, note="Team/learning pace."),
    "Phosani's Nightmare": BossRate("Phosani's Nightmare", 5, 12, note="Solo learning/sustainable pace."),
    "Obor": BossRate("Obor", 15, 30, note="Key-gated; rate assumes keys are already banked."),
    "Phantom Muspah": BossRate("Phantom Muspah", 18, 25),
    "Sarachnis": BossRate("Sarachnis", 30, 70, note="Current guidance uses ~30/h for lower-level accounts and up to ~70/h with stronger gear."),
    "Scorpia": BossRate("Scorpia", 45, 72, note="Wilderness interruptions can lower real rate."),
    "Scurrius": BossRate("Scurrius", 30, 40),
    "Shellbane Gryphon": BossRate("Shellbane Gryphon", 40, 56, source_group="strategy / average-gear model", note="Strategy sources place practical rate around 50-65/h with strong setup."),
    "Skotizo": BossRate("Skotizo", 1, 1, unit="kills", note="Dark-totem gated; target assumes a totem is available."),
    "Sol Heredit": BossRate("Sol Heredit", 1.0, 2.5, unit="completions", minimum_session_minutes=60, note="Represents full Colosseum completions, not just boss fight time."),
    "Spindel": BossRate("Spindel", 40, 55, source_group="average-gear drop-rate model", note="Wilderness interruptions can lower real rate."),
    "Tempoross": BossRate("Tempoross", 10, 12, unit="games", note="About five to six minutes per standard game; reward-point methods can differ."),
    "The Gauntlet": BossRate("The Gauntlet", 7, 10, unit="completions", minimum_session_minutes=15),
    "The Corrupted Gauntlet": BossRate("The Corrupted Gauntlet", 4, 6, unit="completions", minimum_session_minutes=15, note="Current guides commonly use 4-6 completions/h for non-max play."),
    "The Hueycoatl": BossRate("The Hueycoatl", 5, 7, unit="completions", note="Group-size dependent."),
    "The Leviathan": BossRate("The Leviathan", 15, 24),
    "The Royal Titans": BossRate("The Royal Titans", 30, 48, unit="completions"),
    "The Whisperer": BossRate("The Whisperer", 12, 20),
    "Theatre of Blood": BossRate("Theatre of Blood", 1.5, 3.0, unit="raids", minimum_session_minutes=30, note="Team and wipe rate heavily affect throughput."),
    "Theatre of Blood: Hard Mode": BossRate("Theatre of Blood: Hard Mode", 1.0, 2.0, unit="raids", minimum_session_minutes=45, note="Experienced-team content; conservative target."),
    "Thermonuclear Smoke Devil": BossRate("Thermonuclear Smoke Devil", 50, 80),
    "Tombs of Amascut": BossRate("Tombs of Amascut", 1.5, 3.0, unit="raids", minimum_session_minutes=30, note="Normal-invocation late-mid pace."),
    "Tombs of Amascut: Expert Mode": BossRate("Tombs of Amascut: Expert Mode", 1.0, 1.75, unit="raids", minimum_session_minutes=45, note="Wiki-derived expert solo benchmark ~1.75/h; late-mid target is lower."),
    "TzKal-Zuk": BossRate("TzKal-Zuk", 0.6, 1.0, unit="completions", minimum_session_minutes=90, note="Full Inferno completion; short sessions are not offered as KC goals."),
    "TzTok-Jad": BossRate("TzTok-Jad", 1.0, 1.5, unit="completions", minimum_session_minutes=60, note="Full Fight Caves completion."),
    "Vardorvis": BossRate("Vardorvis", 22, 28, source_group="average-gear / wiki-derived benchmark"),
    "Venenatis": BossRate("Venenatis", 15, 24, source_group="average-gear drop-rate model", note="Wilderness interruptions can lower real rate."),
    "Vet'ion": BossRate("Vet'ion", 20, 32, source_group="average-gear drop-rate model", note="Wilderness interruptions can lower real rate."),
    "Vorkath": BossRate("Vorkath", 22, 30, source_group="wiki-derived money guide", note="22/h aligns with budget/blowpipe benchmark; stronger dragonbane setups reach ~30/h."),
    "Wintertodt": BossRate("Wintertodt", 10, 12, unit="games", note="Standard group games; long solos and world-hopping methods differ."),
    "Yama": BossRate("Yama", 7, 10, source_group="wiki-derived money guide", note="Current solo money guide assumes ~10/h; late-mid target leaves learning/death margin."),
    "Zalcano": BossRate("Zalcano", 13, 48, unit="completions", note="~13/h is a documented four-person-group assumption; themed mass worlds can approach ~48/h."),
    "Zulrah": BossRate("Zulrah", 15, 20, source_group="wiki-derived money guide", note="Wiki guide commonly assumes ~20/h; late-mid target leaves rotation/banking margin."),
}


def boss_rate(name: str) -> BossRate | None:
    return BOSS_RATES.get(name)


def all_boss_names() -> list[str]:
    return sorted(BOSS_RATES)
