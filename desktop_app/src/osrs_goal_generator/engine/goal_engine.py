from __future__ import annotations

import random
import uuid
from dataclasses import asdict
from datetime import datetime

from ..account_math import level_progress, lowest_skills, xp_for_level, xp_to_next_level
from ..boss_rates import BOSS_RATES, boss_rate
from ..models import Goal, GoalCandidate, GoalFilters, PathEvaluation, PlayerProfile
from .scoring import ScoreEngine, ScoringContext


BOSS_MARKERS = set(BOSS_RATES)


CLUE_NAMES = {
    "Clue Scrolls (beginner)", "Clue Scrolls (easy)", "Clue Scrolls (medium)",
    "Clue Scrolls (hard)", "Clue Scrolls (elite)", "Clue Scrolls (master)",
}


class GoalEngine:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.scorer = ScoreEngine()

    def generate_candidates(self, profile: PlayerProfile, filters: GoalFilters) -> list[GoalCandidate]:
        candidates: list[GoalCandidate] = []
        if filters.category in {"surprise me", "skilling", "progression"}:
            candidates.extend(self._skill_candidates(profile, filters))
        if filters.category in {"surprise me", "bossing"}:
            candidates.extend(self._boss_candidates(profile, filters))
        if filters.category in {"surprise me", "clues"}:
            candidates.extend(self._clue_candidates(profile, filters))
        if filters.category in {"surprise me", "collection"}:
            candidate = self._collection_candidate(profile, filters)
            if candidate:
                candidates.append(candidate)
        if filters.category in {"surprise me", "money"}:
            candidates.append(self._money_candidate(filters))
        return candidates

    def choose_goal(
        self,
        profile: PlayerProfile,
        filters: GoalFilters,
        context: ScoringContext | None = None,
    ) -> Goal:
        context = context or ScoringContext(session_minutes=filters.session_minutes)
        candidates = [
            candidate
            for candidate in self.generate_candidates(profile, filters)
            if candidate.target_name not in context.blocked_targets
        ]
        if not candidates:
            raise ValueError(
                "No valid goal candidates remain. Check your category or unblock some targets."
            )

        for candidate in candidates:
            self.scorer.score(candidate, context)

        if filters.category == "surprise me":
            selected = self._choose_surprise_candidate(profile, filters, context)
        elif filters.category == "bossing":
            selected = self._choose_bossing_candidate(candidates, context)
        else:
            selected = self._choose_ranked_candidate(candidates, context)
        return self._candidate_to_goal(selected, filters)

    def _choose_ranked_candidate(
        self,
        candidates: list[GoalCandidate],
        context: ScoringContext,
    ) -> GoalCandidate:
        """Choose a recommendation inside one category without deterministic ties."""
        pool = list(candidates)
        if len(pool) > 1 and context.rerolled_targets:
            held_out = set(context.rerolled_targets[: min(8, len(pool) - 1)])
            fresh = [candidate for candidate in pool if candidate.target_name not in held_out]
            if fresh:
                pool = fresh

        self.rng.shuffle(pool)
        pool.sort(key=lambda candidate: candidate.score.total, reverse=True)
        pool = pool[: min(7, len(pool))]
        floor = min(candidate.score.total for candidate in pool)
        weights = [max(1.0, (candidate.score.total - floor) + 8.0) for candidate in pool]
        return self.rng.choices(pool, weights=weights, k=1)[0]

    def _choose_surprise_candidate(
        self,
        profile: PlayerProfile,
        filters: GoalFilters,
        context: ScoringContext,
    ) -> GoalCandidate:
        """Pick an activity type first, then a goal inside that activity type.

        Alpha 6.6 and earlier mixed every Surprise Me candidate into one ranked
        list.  Skilling candidates routinely occupied the strongest top-seven
        positions, so Surprise Me behaved like a second Skilling button.

        Surprise Me now gives each *available category* one ticket in the first
        draw.  Only after a category is selected do recommendation scores choose
        a useful target inside that category.  This keeps bossing, clues,
        collection, progression, money-making, and skilling genuinely in play.
        """
        category_order = (
            "skilling",
            "bossing",
            "clues",
            "collection",
            "progression",
            "money",
        )
        groups: dict[str, list[GoalCandidate]] = {}

        for category in category_order:
            category_filters = GoalFilters(
                category=category,
                difficulty=filters.difficulty,
                session_minutes=filters.session_minutes,
            )
            group = [
                candidate
                for candidate in self.generate_candidates(profile, category_filters)
                if candidate.target_name not in context.blocked_targets
            ]
            if not group:
                continue
            for candidate in group:
                self.scorer.score(candidate, context)
            groups[category] = group

        if not groups:
            raise ValueError(
                "No valid Surprise Me categories remain. Check your blocks and account data."
            )

        available_categories = list(groups)
        self.rng.shuffle(available_categories)
        chosen_category = self.rng.choice(available_categories)
        chosen_group = groups[chosen_category]

        if chosen_category == "bossing":
            return self._choose_bossing_candidate(chosen_group, context)
        return self._choose_ranked_candidate(chosen_group, context)

    def _choose_bossing_candidate(
        self,
        candidates: list[GoalCandidate],
        context: ScoringContext,
    ) -> GoalCandidate:
        """Choose from the full eligible boss pool with bounded score weighting.

        Earlier builds ranked bosses and then sampled only the top seven. When
        many bosses tied, stable sorting preserved alphabetical generation
        order, so rerolls appeared to cycle through a tiny alphabetical group.

        Bossing-only generation now keeps every eligible boss in play. The
        most recent rerolls are temporarily excluded when alternatives exist,
        and recommendation score influences probability without overwhelming
        variety.
        """
        pool = list(candidates)
        if len(pool) > 1 and context.rerolled_targets:
            held_out = set(context.rerolled_targets[: min(8, len(pool) - 1)])
            fresh = [c for c in pool if c.target_name not in held_out]
            if fresh:
                pool = fresh

        # Shuffle first so equal-score candidates never retain alphabetical
        # order. Weighted selection then samples the entire remaining pool.
        self.rng.shuffle(pool)
        floor = min(c.score.total for c in pool)
        weights: list[float] = []
        for candidate in pool:
            score_advantage = max(0.0, candidate.score.total - floor)
            # Cap score influence at 4x the baseline so progression-relevant
            # bosses are favored without making ordinary bosses unreachable.
            weights.append(1.0 + min(3.0, score_advantage / 10.0))
        return self.rng.choices(pool, weights=weights, k=1)[0]

    def choose_boss_goal(
        self,
        profile: PlayerProfile,
        boss_name: str,
        filters: GoalFilters,
        context: ScoringContext | None = None,
    ) -> Goal:
        context = context or ScoringContext(session_minutes=filters.session_minutes)
        if boss_name in context.blocked_targets:
            raise ValueError(f"{boss_name} is currently blocked in your preferences.")
        candidate = self._boss_candidate(profile, boss_name, filters)
        if candidate is None:
            rate = boss_rate(boss_name)
            if rate and not rate.targetable:
                raise ValueError(f"{boss_name} is a special encounter and is not offered as a farmable KC goal.")
            if rate and filters.session_minutes < rate.minimum_session_minutes:
                raise ValueError(
                    f"{boss_name} needs at least a {rate.minimum_session_minutes}-minute session "
                    "for a realistic completion target."
                )
            raise ValueError(f"No calibrated boss-goal rate is available for {boss_name}.")
        self.scorer.score(candidate, context)
        return self._candidate_to_goal(candidate, filters)

    def choose_path_goal(
        self,
        profile: PlayerProfile,
        evaluation: PathEvaluation,
        filters: GoalFilters,
        context: ScoringContext | None = None,
    ) -> Goal:
        """Generate a task specifically for a path's current measurable blocker."""
        context = context or ScoringContext(session_minutes=filters.session_minutes)
        blocker = evaluation.current_blocker
        if blocker is None:
            raise ValueError(f"{evaluation.path.name} has no remaining measurable blocker.")

        requirement = blocker.requirement
        reason = f"This directly advances your {evaluation.path.name} path."

        if requirement.kind == "skill":
            skill = profile.skill(requirement.target)
            if skill is None or skill.level >= 99:
                raise ValueError(f"No trainable skill target is available for {requirement.target}.")
            candidate = self._skill_candidate(
                skill,
                filters,
                category="progression",
                progression_value=20,
                extra_reasons=[reason, f"Current path requirement: {requirement.label}."],
            )
        elif requirement.kind == "base_level":
            target_level = int(requirement.required_value or 0)
            skills = [
                skill
                for skill in lowest_skills(profile, 24)
                if skill.level < target_level
            ]
            if not skills:
                raise ValueError(f"No skill remains below {target_level}.")
            skill = skills[0]
            candidate = self._skill_candidate(
                skill,
                filters,
                category="progression",
                progression_value=22,
                extra_reasons=[
                    reason,
                    f"{skill.name} is currently your lowest skill below the {requirement.label} target.",
                ],
            )
        elif requirement.kind == "total_level":
            skills = lowest_skills(profile, 8)
            if not skills:
                raise ValueError("No trainable skill is available for this total-level path.")
            skill = skills[0]
            candidate = self._skill_candidate(
                skill,
                filters,
                category="progression",
                progression_value=18,
                extra_reasons=[
                    reason,
                    f"Every skill level contributes toward {requirement.label}; {skill.name} is one of your lowest skills.",
                ],
            )
        elif requirement.kind == "boss_kc":
            candidate = self._boss_candidate(profile, requirement.target, filters)
            if candidate is None:
                raise ValueError(f"No calibrated boss goal is available for {requirement.target}.")
            candidate.category = "progression"
            candidate.metadata["progression_value"] = 20
            candidate.reasons.insert(0, reason)
        else:
            raise ValueError(f"{evaluation.path.name} does not have an auto-generatable blocker yet.")

        if candidate.target_name in context.blocked_targets:
            raise ValueError(f"{candidate.target_name} is currently blocked in your preferences.")
        self.scorer.score(candidate, context)
        candidate.metadata["source_path_id"] = evaluation.path.path_id
        candidate.metadata["source_path_name"] = evaluation.path.name
        return self._candidate_to_goal(candidate, filters)

    def _candidate_to_goal(self, selected: GoalCandidate, filters: GoalFilters) -> Goal:
        breakdown = asdict(selected.score)
        breakdown["total"] = selected.score.total

        reasons = list(selected.reasons)
        score_reasons = self._score_reasons(selected)
        for reason in score_reasons:
            if reason not in reasons:
                reasons.append(reason)

        metadata = dict(selected.metadata)
        metadata["difficulty"] = filters.difficulty
        metadata["session_minutes"] = filters.session_minutes

        return Goal(
            goal_id=uuid.uuid4().hex[:12],
            generated_at=datetime.now().isoformat(timespec="seconds"),
            category=selected.category,
            subtype=selected.subtype,
            target_name=selected.target_name,
            title=selected.title,
            objective=selected.objective,
            reasons=reasons[:4],
            bonus=selected.metadata.get("bonus"),
            start_value=selected.start_value,
            target_value=selected.target_value,
            estimated_minutes=selected.estimated_minutes,
            score=selected.score.total,
            score_breakdown=breakdown,
            metadata=metadata,
        )

    def _score_reasons(self, candidate: GoalCandidate) -> list[str]:
        score = candidate.score
        reasons: list[str] = []
        if score.active_path > 0:
            reasons.append("This directly supports one of your active long-term paths.")
        if score.blocker > 0:
            reasons.append("This removes a current progression blocker.")
        if score.cross_path > 0:
            reasons.append("This advances more than one active progression path.")
        if score.proximity >= 12:
            reasons.append("You are already close to finishing the current level.")
        if score.session_fit >= 15:
            reasons.append("The target closely matches your selected session length.")
        if score.preference > 0:
            reasons.append("This category matches your saved preferences.")
        if score.variety > 0:
            reasons.append("This gives you variety compared with recent goals.")
        return reasons

    def _skill_candidate(
        self,
        skill,
        filters: GoalFilters,
        *,
        category: str | None = None,
        progression_value: int = 10,
        extra_reasons: list[str] | None = None,
    ) -> GoalCandidate:
        remaining = xp_to_next_level(skill)
        progress = level_progress(skill) or 0.0
        if remaining is None:
            raise ValueError(f"{skill.name} is not currently trainable.")

        fraction = {15: 0.18, 30: 0.30, 60: 0.50}.get(filters.session_minutes, 0.70)
        if filters.difficulty == "chill":
            fraction *= 0.75
        elif filters.difficulty == "grind":
            fraction *= 1.30
        target_xp = max(1_000, min(remaining, int(remaining * fraction)))

        if target_xp >= remaining * 0.85:
            objective = (
                f"Train {skill.name} from {skill.level} -> {skill.level + 1}. "
                f"About {remaining:,} XP remains."
            )
            target_value = xp_for_level(skill.level + 1)
            subtype = "skill_level"
        else:
            objective = f"Gain {target_xp:,} XP in {skill.name}. Current level: {skill.level}."
            target_value = skill.xp + target_xp
            subtype = "skill_xp"

        reasons = [
            f"{skill.name} is one of your lower trainable skills.",
            f"You are about {progress * 100:.0f}% through the current level.",
        ]
        if extra_reasons:
            reasons = list(extra_reasons) + reasons

        return GoalCandidate(
            category=category or ("skilling" if filters.category != "progression" else "progression"),
            subtype=subtype,
            target_name=skill.name,
            title=f"{skill.name} Progress",
            objective=objective,
            reasons=reasons,
            start_value=skill.xp,
            target_value=target_value,
            estimated_minutes=filters.session_minutes,
            metadata={
                "progression_value": progression_value,
                "level_progress": progress,
                "start_level": skill.level,
                "target_level": skill.level + 1 if subtype == "skill_level" else None,
                "bonus": f"Long-term: keep pushing {skill.name} toward the next useful milestone.",
            },
        )

    def _skill_candidates(self, profile: PlayerProfile, filters: GoalFilters) -> list[GoalCandidate]:
        candidates: list[GoalCandidate] = []
        for skill in lowest_skills(profile, 8):
            try:
                candidates.append(self._skill_candidate(skill, filters))
            except ValueError:
                continue
        return candidates

    def _boss_candidate(
        self,
        profile: PlayerProfile,
        name: str,
        filters: GoalFilters,
    ) -> GoalCandidate | None:
        rate = boss_rate(name)
        if rate is None or name not in BOSS_MARKERS:
            return None

        increment = rate.target_increment(filters.session_minutes, filters.difficulty)
        if increment is None:
            return None

        activity = profile.activity(name)
        current = max(0, activity.score) if activity else 0
        effective_rate = rate.effective_rate(filters.difficulty) or 0.0
        benchmark_text = (
            f" Guide benchmark/cap: ~{rate.benchmark_rate:g} {rate.unit}/h."
            if rate.benchmark_rate
            else ""
        )

        unit_title = rate.unit if rate.unit == "KC" else rate.unit.title()
        title = name if name.lower().endswith(rate.unit.lower()) else f"{name} {unit_title}"

        return GoalCandidate(
            category="bossing",
            subtype="boss_kc",
            target_name=name,
            title=title,
            objective=(
                f"Push {name} from {current:,} -> {current + increment:,} "
                f"{rate.unit.lower()}."
            ),
            reasons=[
                (
                    f"The app estimates a sustainable late-mid pace of "
                    f"~{rate.late_mid_rate:g} {rate.unit}/h for Moderate."
                ),
                (
                    f"Your {filters.difficulty.title()} setting uses about "
                    f"{effective_rate:g} {rate.unit}/h for this target."
                    + benchmark_text
                ),
            ],
            start_value=current,
            target_value=current + increment,
            estimated_minutes=filters.session_minutes,
            metadata={
                "progression_value": 7,
                "boss_late_mid_rate": rate.late_mid_rate,
                "boss_effective_rate": effective_rate,
                "boss_benchmark_rate": rate.benchmark_rate,
                "boss_unit": rate.unit,
                "boss_rate_confidence": rate.confidence,
                "boss_rate_note": rate.note,
                "bonus": f"Stay at {name} for the full session if you finish the target early.",
            },
        )

    def _boss_candidates(self, profile: PlayerProfile, filters: GoalFilters) -> list[GoalCandidate]:
        candidates: list[GoalCandidate] = []
        for name in sorted(BOSS_MARKERS):
            candidate = self._boss_candidate(profile, name, filters)
            if candidate:
                candidates.append(candidate)
        return candidates

    def _clue_candidates(self, profile: PlayerProfile, filters: GoalFilters) -> list[GoalCandidate]:
        candidates: list[GoalCandidate] = []
        amount = {"chill": 1, "moderate": 3, "grind": 5}.get(filters.difficulty, 3)
        for name in CLUE_NAMES:
            activity = profile.activity(name)
            if activity is None or activity.score < 0:
                continue
            tier = name.removeprefix("Clue Scrolls (").removesuffix(")").title()
            candidates.append(GoalCandidate(
                category="clues",
                subtype="clue_count",
                target_name=name,
                title=f"{tier} Clues",
                objective=(
                    f"Complete {amount} {tier.lower()} clue{'s' if amount != 1 else ''}. "
                    f"Current tracked total: {activity.score:,}."
                ),
                reasons=[
                    "This uses your public clue-scroll HiScores.",
                    "The count scales with your selected intensity.",
                ],
                start_value=activity.score,
                target_value=activity.score + amount,
                estimated_minutes=filters.session_minutes,
                metadata={"progression_value": 5},
            ))
        return candidates

    def _collection_candidate(self, profile: PlayerProfile, filters: GoalFilters) -> GoalCandidate | None:
        activity = profile.activity("Collections Logged")
        if activity is None or activity.score < 0:
            return None
        increment = {"chill": 1, "moderate": 2, "grind": 3}.get(filters.difficulty, 2)
        return GoalCandidate(
            category="collection",
            subtype="collection_logged",
            target_name="Collections Logged",
            title="Collection Log Hunt",
            objective=f"Try to move Collections Logged from {activity.score:,} -> {activity.score + increment:,}.",
            reasons=[
                "Your public Collections Logged score is available.",
                "The app does not assume which specific slots you are missing.",
            ],
            start_value=activity.score,
            target_value=activity.score + increment,
            estimated_minutes=filters.session_minutes,
            metadata={"progression_value": 8},
        )

    def _money_candidate(self, filters: GoalFilters) -> GoalCandidate:
        base = {15: 100_000, 30: 250_000, 60: 500_000}.get(filters.session_minutes, 1_000_000)
        multiplier = {"chill": 1, "moderate": 2, "grind": 4}.get(filters.difficulty, 2)
        target = base * multiplier
        return GoalCandidate(
            category="money",
            subtype="gp_profit",
            target_name="GP",
            title="Cash Stack",
            objective=f"Bank at least {target:,} GP in profit during this session.",
            reasons=[
                "GP is not public HiScores data, so this target is sized from your session settings.",
                "This remains a manual-completion goal until we have a safe account-data source for bank value.",
            ],
            start_value=0,
            target_value=target,
            estimated_minutes=filters.session_minutes,
            metadata={"progression_value": 4},
        )
