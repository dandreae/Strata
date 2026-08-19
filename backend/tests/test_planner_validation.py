from __future__ import annotations

import math

from app.agent.planner_schema import CandidateProposal
from app.agent.planner_validation import (
    INFILL_MAX_PERCENT,
    INFILL_MIN_PERCENT,
    LAYER_HEIGHT_MAX_MM,
    LAYER_HEIGHT_MIN_MM,
    MAX_CANDIDATES_PER_ROUND,
    PERIMETER_MAX,
    PERIMETER_MIN,
    validate_and_normalize_proposals,
)


def _proposal(layer_height=0.20, infill_percent=20, perimeter_count=2) -> CandidateProposal:
    return CandidateProposal(layer_height=layer_height, infill_percent=infill_percent, perimeter_count=perimeter_count)


# --- valid proposals accepted -------------------------------------------


def test_valid_proposal_set_accepted() -> None:
    proposals = [
        _proposal(0.15, 10, 2),
        _proposal(0.20, 20, 3),
        _proposal(0.25, 30, 4),
    ]
    outcome = validate_and_normalize_proposals("run-1", proposals, requested_count=3)

    assert len(outcome.accepted) == 3
    assert outcome.rejected == []
    assert all(c.run_id == "run-1" for c in outcome.accepted)
    # Fixed, non-planner-controlled fields:
    assert all(c.supports_enabled is False for c in outcome.accepted)
    assert all(c.orientation_x == 0.0 and c.orientation_y == 0.0 and c.orientation_z == 0.0 for c in outcome.accepted)


def test_infill_percent_normalized_to_int() -> None:
    outcome = validate_and_normalize_proposals("run-1", [_proposal(infill_percent=17.6)], requested_count=1)
    assert outcome.accepted[0].infill_percent == 18  # rounded
    assert isinstance(outcome.accepted[0].infill_percent, int)


# --- bounds ---------------------------------------------------------


def test_rejects_layer_height_out_of_bounds() -> None:
    outcome = validate_and_normalize_proposals("run-1", [_proposal(layer_height=5)], requested_count=1)
    assert outcome.accepted == []
    assert "layer_height" in outcome.rejected[0]


def test_rejects_negative_infill() -> None:
    outcome = validate_and_normalize_proposals("run-1", [_proposal(infill_percent=-20)], requested_count=1)
    assert outcome.accepted == []
    assert "infill_percent" in outcome.rejected[0]


def test_rejects_excessive_perimeters() -> None:
    outcome = validate_and_normalize_proposals("run-1", [_proposal(perimeter_count=100)], requested_count=1)
    assert outcome.accepted == []
    assert "perimeter_count" in outcome.rejected[0]


def test_boundary_values_are_accepted_inclusive() -> None:
    proposals = [
        _proposal(LAYER_HEIGHT_MIN_MM, INFILL_MIN_PERCENT, PERIMETER_MIN),
        _proposal(LAYER_HEIGHT_MAX_MM, INFILL_MAX_PERCENT, PERIMETER_MAX),
    ]
    outcome = validate_and_normalize_proposals("run-1", proposals, requested_count=2)
    assert len(outcome.accepted) == 2
    assert outcome.rejected == []


# --- NaN / Infinity --------------------------------------------------


def test_rejects_nan_layer_height() -> None:
    outcome = validate_and_normalize_proposals("run-1", [_proposal(layer_height=math.nan)], requested_count=1)
    assert outcome.accepted == []
    assert "finite" in outcome.rejected[0]


def test_rejects_infinite_infill() -> None:
    outcome = validate_and_normalize_proposals("run-1", [_proposal(infill_percent=math.inf)], requested_count=1)
    assert outcome.accepted == []
    assert "finite" in outcome.rejected[0]


# --- duplicates -------------------------------------------------------


def test_rejects_duplicate_proposals() -> None:
    proposals = [_proposal(0.20, 20, 2), _proposal(0.20, 20, 2)]
    outcome = validate_and_normalize_proposals("run-1", proposals, requested_count=2)

    assert len(outcome.accepted) == 1
    assert len(outcome.rejected) == 1
    assert "duplicate" in outcome.rejected[0]


def test_near_duplicate_after_rounding_is_rejected() -> None:
    # 17.4 and 17.6 both round to int 17/18 differently... use values that
    # collide only after normalization to prove dedup happens post-round.
    proposals = [_proposal(0.201, 20.4, 2), _proposal(0.199, 19.6, 2)]
    outcome = validate_and_normalize_proposals("run-1", proposals, requested_count=2)
    # Both round to layer_height=0.20, infill=20 -> genuine duplicate after normalization.
    assert len(outcome.accepted) == 1
    assert len(outcome.rejected) == 1


# --- candidate count limits ---------------------------------------------


def test_does_not_exceed_requested_count() -> None:
    proposals = [_proposal(0.15 + 0.01 * i, 10 + i, 2) for i in range(5)]
    outcome = validate_and_normalize_proposals("run-1", proposals, requested_count=3)

    assert len(outcome.accepted) == 3
    assert len(outcome.rejected) == 2
    assert all("exceeds" in r for r in outcome.rejected)


def test_hard_ceiling_caps_even_a_large_request() -> None:
    proposals = [_proposal(0.10 + 0.01 * i, 5 + i, 2) for i in range(20)]
    outcome = validate_and_normalize_proposals("run-1", proposals, requested_count=1000)

    assert len(outcome.accepted) == MAX_CANDIDATES_PER_ROUND
    assert len(outcome.rejected) == 20 - MAX_CANDIDATES_PER_ROUND


def test_empty_proposal_list_yields_empty_outcome() -> None:
    outcome = validate_and_normalize_proposals("run-1", [], requested_count=8)
    assert outcome.accepted == []
    assert outcome.rejected == []


# --- mixed valid/invalid -------------------------------------------------


def test_valid_and_invalid_proposals_are_independently_classified() -> None:
    proposals = [
        _proposal(0.20, 20, 2),  # valid
        _proposal(5.0, 20, 2),  # invalid: layer_height
        _proposal(0.20, -5, 2),  # invalid: infill
        _proposal(0.20, 25, 2),  # valid, distinct from the first
    ]
    outcome = validate_and_normalize_proposals("run-1", proposals, requested_count=4)

    assert len(outcome.accepted) == 2
    assert len(outcome.rejected) == 2


# --- round tracking / cross-round duplicates (round 2) --------------------


def test_round_number_is_stamped_on_accepted_candidates() -> None:
    outcome = validate_and_normalize_proposals("run-1", [_proposal(0.20, 20, 2)], requested_count=1, round_number=2)
    assert outcome.accepted[0].round == 2


def test_round_number_defaults_to_one() -> None:
    outcome = validate_and_normalize_proposals("run-1", [_proposal(0.20, 20, 2)], requested_count=1)
    assert outcome.accepted[0].round == 1


def test_rejects_duplicate_of_an_existing_round_one_candidate() -> None:
    from app.models.candidate import CandidateConfiguration

    round1 = [CandidateConfiguration(run_id="run-1", layer_height=0.20, infill_percent=20, perimeter_count=2)]
    outcome = validate_and_normalize_proposals(
        "run-1", [_proposal(0.20, 20, 2)], requested_count=1, existing=round1, round_number=2
    )

    assert outcome.accepted == []
    assert len(outcome.rejected) == 1
    assert "duplicate" in outcome.rejected[0]


def test_round_two_proposal_distinct_from_round_one_is_accepted() -> None:
    from app.models.candidate import CandidateConfiguration

    round1 = [CandidateConfiguration(run_id="run-1", layer_height=0.20, infill_percent=20, perimeter_count=2)]
    outcome = validate_and_normalize_proposals(
        "run-1", [_proposal(0.15, 10, 3)], requested_count=1, existing=round1, round_number=2
    )

    assert len(outcome.accepted) == 1
    assert outcome.accepted[0].round == 2
    assert outcome.rejected == []


def test_existing_none_behaves_like_no_prior_round() -> None:
    outcome = validate_and_normalize_proposals("run-1", [_proposal(0.20, 20, 2)], requested_count=1, existing=None)
    assert len(outcome.accepted) == 1
