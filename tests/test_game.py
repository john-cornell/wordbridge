import pytest

from wordbridge.game import Chain


def test_add_word_computes_similarities(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.99)
    step = chain.add_word("dog")
    assert step.word == "dog"
    assert step.neighbor_similarity == pytest.approx(tiny_model.similarity("dog", "cat"))
    assert step.target_similarity == pytest.approx(tiny_model.similarity("dog", "auto"))


def test_digression_detected_when_target_similarity_drops(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.99)
    chain.add_word("car")   # much closer to target than the cat->auto baseline
    step = chain.add_word("dog")  # further from target than car was -> digression
    assert step.is_digression is True


def test_add_word_rejects_unknown_word(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    with pytest.raises(ValueError):
        chain.add_word("nonexistent")


def test_is_won_when_graph_connects_start_to_target(tiny_model):
    # threshold=0.05: cat-dog and dog-auto both clear it, so "dog" bridges
    # start to target even though cat-auto direct similarity is ~0.0.
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.05)
    assert chain.is_won() is False
    chain.add_word("dog")
    assert chain.is_won() is True


def test_is_won_false_when_played_words_form_disconnected_islands(tiny_model):
    # "dog" only bridges to "cat" here (dog-auto similarity is below threshold),
    # so it's an island that never reaches the target.
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    chain.add_word("dog")
    assert chain.is_won() is False


def test_closest_unconnected_pair_with_no_steps_is_start_and_target(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    assert chain.closest_unconnected_pair() == ("cat", "auto")


def test_closest_unconnected_pair_prefers_the_closest_cross_component_bridge(tiny_model):
    # After "dog" (joins cat's component), the closest still-unconnected pair
    # should be dog<->auto (0.11), not cat<->auto (0.0).
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    chain.add_word("dog")
    anchor, other = chain.closest_unconnected_pair()
    assert {anchor, other} == {"dog", "auto"}


def test_winning_connection_returns_none_when_not_won(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    chain.add_word("dog")
    assert chain.winning_connection() is None


def test_winning_connection_returns_path_with_similarities(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.05)
    chain.add_word("dog")

    connection = chain.winning_connection()

    assert connection == [
        {"a": "cat", "b": "dog", "similarity": pytest.approx(tiny_model.similarity("cat", "dog"))},
        {"a": "dog", "b": "auto", "similarity": pytest.approx(tiny_model.similarity("dog", "auto"))},
    ]


def test_score_scales_by_difficulty_multiplier(tiny_model):
    # multiplier = threshold / 0.5 -> Normal (0.5) is 1x, Hard (0.7) is 1.4x, Easy (0.25) is 0.5x
    easy = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.25)
    normal = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    hard = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.7)
    for chain in (easy, normal, hard):
        chain.add_word("dog")  # 1 step, 0 digressions, 0 hints -> raw score 90

    assert easy.score() == 45
    assert normal.score() == 90
    assert hard.score() == 126


def test_score_penalizes_length_and_digressions(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.99)
    chain.add_word("car")
    chain.add_word("dog")  # digression, per test above
    raw = 100 - (10 * 2) - (5 * 1)
    assert chain.score() == round(raw * (0.99 / 0.5))  # threshold=0.99 -> 1.98x multiplier


def test_score_is_100_when_actual_words_match_par(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.99, par_length=2)
    chain.add_word("dog")
    chain.add_word("car")
    assert chain.score() == 100


def test_score_drops_relative_to_par_as_extra_words_are_used(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.99, par_length=1)
    chain.add_word("dog")
    chain.add_word("car")  # 2 words used against a par of 1 -> 100*1/2
    assert chain.score() == 50


def test_score_counts_a_digression_as_an_extra_effective_word(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.99, par_length=1)
    chain.add_word("car")
    chain.add_word("dog")  # digression, per test above
    # effective_words = 2 played + 1 digression penalty -> 100*1/3
    assert chain.score() == round(100 * 1 / 3)


def test_score_counts_a_hint_as_two_extra_effective_words(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", par_length=1)  # default threshold=0.7
    chain.use_hint()
    chain.use_hint()
    # no steps played, but effective_words = 2 hints * 2 -> 100*1/4
    assert chain.score() == round(100 * 1 / 4)


def test_score_falls_back_to_legacy_difficulty_formula_when_par_is_unknown(tiny_model):
    # par_length defaults to None (e.g. the model couldn't find any route) —
    # score() must not blow up, it falls back to the old absolute formula.
    easy = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.25)
    normal = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    hard = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.7)
    for chain in (easy, normal, hard):
        chain.add_word("dog")  # 1 step, 0 digressions, 0 hints -> raw score 90

    assert easy.score() == 45
    assert normal.score() == 90
    assert hard.score() == 126


def test_par_length_round_trips_through_to_dict_and_from_dict(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", par_length=3)
    restored = Chain.from_dict(tiny_model, chain.to_dict())
    assert restored.par_length == 3


def test_solution_route_round_trips_but_solution_trace_does_not(tiny_model):
    # solution_trace can be tens of KB (many hops x many candidates each) -
    # it must never ride in the session cookie (confirmed in production,
    # 2026-08-24: this blew past browsers' ~4KB cookie limit and got
    # sessions silently dropped mid-game). solution_route is small (just a
    # list of words) and is fine to round-trip.
    chain = Chain(
        tiny_model,
        start_word="cat",
        target_word="auto",
        solution_route=["cat", "dog", "auto"],
        solution_trace=[{"from": "cat", "candidates": [], "chosen": "dog"}],
    )

    serialized = chain.to_dict()
    assert "solution_trace" not in serialized
    assert serialized["solution_route"] == ["cat", "dog", "auto"]

    restored = Chain.from_dict(tiny_model, serialized)
    assert restored.solution_route == ["cat", "dog", "auto"]
    assert restored.solution_trace is None


def test_is_over_soft_cap(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", soft_cap=1)
    chain.add_word("car")
    assert chain.is_over_soft_cap() is False
    chain.add_word("dog")
    assert chain.is_over_soft_cap() is True


def test_restart_clears_steps(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    chain.add_word("car")
    chain.restart()
    assert chain.steps == []


def test_chain_starts_not_completed(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    assert chain.completed is False


def test_mark_completed_sets_completed_flag(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    chain.mark_completed()
    assert chain.completed is True


def test_completed_round_trips_through_to_dict_and_from_dict(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    chain.add_word("car")
    chain.mark_completed()

    restored = Chain.from_dict(tiny_model, chain.to_dict())

    assert restored.completed is True


def test_not_completed_round_trips_through_to_dict_and_from_dict(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    chain.add_word("car")

    restored = Chain.from_dict(tiny_model, chain.to_dict())

    assert restored.completed is False


def test_restart_resets_completed_flag(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    chain.mark_completed()
    chain.restart()
    assert chain.completed is False


def test_mark_won_sets_completed_and_won_flags(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    assert chain.won is False
    chain.mark_won()
    assert chain.completed is True
    assert chain.won is True


def test_restart_resets_won_flag(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    chain.mark_won()
    chain.restart()
    assert chain.won is False


def test_add_word_records_similarities_to_every_other_word(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.99)
    chain.add_word("car")
    step = chain.add_word("dog")

    similarities_by_word = {entry["word"]: entry["similarity"] for entry in step.similarities}
    assert similarities_by_word["cat"] == pytest.approx(tiny_model.similarity("dog", "cat"))
    assert similarities_by_word["auto"] == pytest.approx(tiny_model.similarity("dog", "auto"))
    assert similarities_by_word["car"] == pytest.approx(tiny_model.similarity("dog", "car"))
    assert len(step.similarities) == 3


def test_first_word_similarities_cover_only_start_and_target(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    step = chain.add_word("car")
    words_compared = {entry["word"] for entry in step.similarities}
    assert words_compared == {"cat", "auto"}


def test_start_target_similarity_matches_model_similarity(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    assert chain.start_target_similarity() == pytest.approx(
        tiny_model.similarity("cat", "auto")
    )


def test_best_step_returns_none_when_no_steps(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    assert chain.best_step() is None


def test_best_step_returns_step_with_highest_target_similarity(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.99)
    chain.add_word("car")  # target_similarity ~0.99 vs auto
    chain.add_word("dog")  # target_similarity ~0.11 vs auto - lower, must not win out
    best = chain.best_step()
    assert best.word == "car"
    assert best.target_similarity == pytest.approx(
        tiny_model.similarity("car", "auto")
    )


def test_add_word_rejects_word_already_played_as_a_step(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    chain.add_word("dog")
    with pytest.raises(ValueError):
        chain.add_word("dog")


def test_add_word_rejects_start_word(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    with pytest.raises(ValueError):
        chain.add_word("cat")


def test_add_word_rejects_target_word(tiny_model):
    # The target word is already "played" by definition — it's the
    # destination, not a move you can make, so it's rejected outright,
    # even on the very first attempt, just like the start word.
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    with pytest.raises(ValueError):
        chain.add_word("auto")


def test_next_hint_cost_starts_at_five_and_doubles(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    assert chain.next_hint_cost() == 5
    chain.use_hint()
    assert chain.next_hint_cost() == 10
    chain.use_hint()
    assert chain.next_hint_cost() == 20
    chain.use_hint()
    assert chain.next_hint_cost() == 40


def test_use_hint_returns_cost_and_accumulates_into_score(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")  # default threshold=0.7
    assert chain.use_hint() == 5
    assert chain.use_hint() == 10
    raw = 100 - 15  # no steps/digressions yet, just hint cost
    assert chain.score() == round(raw * (0.7 / 0.5))  # threshold=0.7 -> 1.4x multiplier


def test_restart_resets_hint_state(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    chain.use_hint()
    chain.restart()
    assert chain.hints_used == 0
    assert chain.hint_cost_total == 0
    assert chain.next_hint_cost() == 5
