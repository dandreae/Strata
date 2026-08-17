from __future__ import annotations

from app.agent.default_candidate import build_default_candidate, generate_candidate_set


def test_generates_expected_number_of_candidates() -> None:
    candidates = generate_candidate_set("run-1")
    assert 6 <= len(candidates) <= 8


def test_generated_configurations_are_unique() -> None:
    candidates = generate_candidate_set("run-1")
    configs = {(c.layer_height, c.infill_percent, c.perimeter_count) for c in candidates}
    assert len(configs) == len(candidates)


def test_values_within_expected_bounds() -> None:
    candidates = generate_candidate_set("run-1")
    for c in candidates:
        assert 0.10 <= c.layer_height <= 0.30
        assert 0 <= c.infill_percent <= 100
        assert c.perimeter_count >= 1


def test_does_not_vary_unverified_parameters() -> None:
    """Orientation and supports are deliberately not varied yet — see
    module docstring in app/agent/default_candidate.py."""
    candidates = generate_candidate_set("run-1")
    assert all(c.orientation_x == 0.0 and c.orientation_y == 0.0 and c.orientation_z == 0.0 for c in candidates)
    assert all(c.supports_enabled is False for c in candidates)


def test_generation_is_deterministic() -> None:
    a = generate_candidate_set("run-1")
    b = generate_candidate_set("run-1")
    a_specs = [(c.layer_height, c.infill_percent, c.perimeter_count) for c in a]
    b_specs = [(c.layer_height, c.infill_percent, c.perimeter_count) for c in b]
    assert a_specs == b_specs


def test_all_candidates_belong_to_the_given_run() -> None:
    candidates = generate_candidate_set("run-42")
    assert all(c.run_id == "run-42" for c in candidates)


def test_candidate_ids_are_distinct() -> None:
    candidates = generate_candidate_set("run-1")
    assert len({c.id for c in candidates}) == len(candidates)


def test_build_default_candidate_still_works_standalone() -> None:
    candidate = build_default_candidate("run-1")
    assert candidate.layer_height == 0.20
    assert candidate.infill_percent == 20
    assert candidate.perimeter_count == 2
    assert candidate.supports_enabled is False
