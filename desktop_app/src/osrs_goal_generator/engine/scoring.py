from __future__ import annotations

from dataclasses import dataclass, field

from ..models import GoalCandidate, ScoreBreakdown


@dataclass(slots=True)
class ScoringContext:
    session_minutes: int
    active_path_targets: set[str] = field(default_factory=set)
    blocker_targets: set[str] = field(default_factory=set)
    preferred_categories: set[str] = field(default_factory=set)
    disliked_categories: set[str] = field(default_factory=set)
    recent_targets: list[str] = field(default_factory=list)
    blocked_targets: set[str] = field(default_factory=set)
    rerolled_targets: list[str] = field(default_factory=list)
    path_target_counts: dict[str, int] = field(default_factory=dict)
    path_priority_bonus: dict[str, float] = field(default_factory=dict)


class ScoreEngine:
    """Recommendation engine v1: the seven factors from our design spec."""

    def score(self, candidate: GoalCandidate, context: ScoringContext) -> ScoreBreakdown:
        breakdown = ScoreBreakdown()

        breakdown.progression = float(candidate.metadata.get("progression_value", 0))

        if candidate.target_name in context.active_path_targets:
            breakdown.active_path = 12.0 + min(10.0, context.path_priority_bonus.get(candidate.target_name, 0.0))
        if candidate.target_name in context.blocker_targets:
            breakdown.blocker = 22.0

        path_count = context.path_target_counts.get(candidate.target_name, 0)
        if path_count > 1:
            breakdown.cross_path = min(15.0, (path_count - 1) * 5.0)

        progress = candidate.metadata.get("level_progress")
        if isinstance(progress, (int, float)):
            if progress >= 0.90:
                breakdown.proximity = 15.0
            elif progress >= 0.75:
                breakdown.proximity = 12.0
            elif progress >= 0.50:
                breakdown.proximity = 8.0
            elif progress >= 0.25:
                breakdown.proximity = 5.0
            else:
                breakdown.proximity = 2.0

        if candidate.estimated_minutes:
            delta = abs(candidate.estimated_minutes - context.session_minutes)
            ratio = delta / max(1, context.session_minutes)
            if ratio <= 0.25:
                breakdown.session_fit = 15.0
            elif ratio <= 0.50:
                breakdown.session_fit = 8.0
            elif ratio <= 1.0:
                breakdown.session_fit = 0.0
            else:
                breakdown.session_fit = -15.0

        if candidate.category in context.preferred_categories:
            breakdown.preference = 10.0
        elif candidate.category in context.disliked_categories:
            breakdown.preference = -12.0

        if candidate.target_name not in context.recent_targets:
            breakdown.variety = 6.0
        else:
            newest_index = context.recent_targets.index(candidate.target_name)
            breakdown.variety = -12.0 if newest_index < 2 else -6.0

        # A reroll means "not this right now", not a permanent dislike.
        if candidate.target_name in context.rerolled_targets:
            reroll_index = context.rerolled_targets.index(candidate.target_name)
            breakdown.variety -= 28.0 if reroll_index < 2 else 16.0

        candidate.score = breakdown
        return breakdown
