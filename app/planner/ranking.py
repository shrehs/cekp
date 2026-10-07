from dataclasses import dataclass
from app.planner.enums import StrategyName, StrategyState

@dataclass(frozen=True)
class RankedCandidate:
    strategy: StrategyName
    routing_score: float
    health_state: StrategyState
    health_penalty: float
    adjusted_score: float
    decision: str

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy.value,
            "routing_score": self.routing_score,
            "health_state": self.health_state.value,
            "health_penalty": self.health_penalty,
            "adjusted_score": self.adjusted_score,
            "decision": self.decision,
        }


def routing_score_from_rank(position: int) -> float:
    return max(0.0, 1.0 - (position * 0.10))


def rank_candidates(
    strategies: list[StrategyName],
    states: dict[StrategyName, StrategyState],
    *,
    health_aware: bool,
    degraded_penalty: float,
) -> list[RankedCandidate]:

    candidates: list[RankedCandidate] = []

    for position, strategy in enumerate(strategies):
        state: StrategyState = states[strategy]
        routing_score = routing_score_from_rank(position)

        if state == StrategyState.UNAVAILABLE:
            candidates.append(
                RankedCandidate(
                    strategy=strategy,
                    routing_score=routing_score,
                    health_state=state,
                    health_penalty=0.0,
                    adjusted_score=float("-inf"),
                    decision="skipped_unavailable",
                )
            )
            continue

        penalty = (
            degraded_penalty
            if health_aware and state == StrategyState.DEGRADED
            else 0.0
        )

        adjusted_score = routing_score - penalty

        candidates.append(
            RankedCandidate(
                strategy=strategy,
                routing_score=routing_score,
                health_state=state,
                health_penalty=penalty,
                adjusted_score=adjusted_score,
                decision="kept",
            )
        )

    original_position = {
        candidate.strategy: index
        for index, candidate in enumerate(candidates)
    }

    live = [
        candidate
        for candidate in candidates
        if candidate.health_state != StrategyState.UNAVAILABLE
    ]

    live.sort(
        key=lambda candidate: (
            -candidate.adjusted_score,
            original_position[candidate.strategy],
        )
    )

    ranked: list[RankedCandidate] = []

    for index, candidate in enumerate(live):
        if index == 0:
            decision = "selected"
        elif candidate.adjusted_score < candidate.routing_score:
            decision = "demoted"
        else:
            decision = "kept"

        ranked.append(
            RankedCandidate(
                strategy=candidate.strategy,
                routing_score=candidate.routing_score,
                health_state=candidate.health_state,
                health_penalty=candidate.health_penalty,
                adjusted_score=candidate.adjusted_score,
                decision=decision,
            )
        )

    ranked.extend(
        RankedCandidate(
            strategy=candidate.strategy,
            routing_score=candidate.routing_score,
            health_state=candidate.health_state,
            health_penalty=0.0,
            adjusted_score=float("-inf"),
            decision="skipped_unavailable",
        )
        for candidate in candidates
        if candidate.health_state == StrategyState.UNAVAILABLE
    )

    return ranked