import pytest

from wordbridge.game import Chain, Step, estimated_par_for_threshold


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


def test_would_win_instantly_true_when_start_and_target_already_connected(tiny_model):
    # cat-dog similarity (~0.99) already clears this threshold on its own.
    chain = Chain(tiny_model, start_word="cat", target_word="dog", threshold=0.5)
    assert chain.would_win_instantly() is True


def test_would_win_instantly_false_when_start_and_target_not_connected(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    assert chain.would_win_instantly() is False


def test_would_win_instantly_false_once_a_word_has_been_played(tiny_model):
    # Threshold is locked once steps exist, so this can only ever matter
    # for the very first word - not after.
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.05)
    chain.add_word("dog")
    chain.threshold = 0.99  # even if it somehow became "instant" in hindsight
    assert chain.would_win_instantly() is False


def test_add_word_rejects_first_word_when_start_and_target_already_connected(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="dog", threshold=0.5)
    try:
        chain.add_word("car")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "already connected at this threshold" in str(exc)
    assert chain.steps == []


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


@pytest.mark.parametrize(
    ("threshold", "expected_par"),
    [(0.1, 1), (0.2, 2), (0.3, 3), (0.4, 5), (0.5, 8), (0.6, 13), (0.8, 21)],
)
def test_estimated_par_matches_exact_anchors(threshold, expected_par):
    assert estimated_par_for_threshold(threshold) == expected_par


@pytest.mark.parametrize(("threshold", "expected_par"), [(0.53, 10), (0.7, 17)])
def test_estimated_par_interpolates_custom_thresholds(threshold, expected_par):
    assert estimated_par_for_threshold(threshold) == expected_par


def test_estimated_par_clamps_thresholds_outside_anchor_range():
    assert estimated_par_for_threshold(0) == 1
    assert estimated_par_for_threshold(1) == 21


def test_score_prefers_real_par_over_estimate(tiny_model):
    chain = Chain(tiny_model, "cat", "auto", threshold=0.8, par_length=1)
    chain.steps = [Step("played", 0, 0, False)]
    assert chain.score() == 100


def test_score_uses_estimated_par_when_real_par_is_unknown(tiny_model):
    chain = Chain(tiny_model, "cat", "auto", threshold=0.53)
    chain.steps = [Step("played", 0, 0, False)] * 10
    assert chain.score() == 100


def test_score_is_100_when_actual_words_match_par(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.99, par_length=2)
    chain.add_word("dog")
    chain.add_word("car")
    assert chain.score() == 100


@pytest.mark.parametrize(
    ("effective_words", "expected_score"),
    [(4, 144), (5, 120), (6, 100), (7, 90), (11, 50), (16, 0), (18, -20)],
)
def test_score_is_exponential_below_par_and_linear_at_or_above_par(
    tiny_model, effective_words, expected_score
):
    chain = Chain(tiny_model, "cat", "auto", par_length=6)
    chain.steps = [Step("played", 0, 0, False)] * effective_words
    assert chain.score() == expected_score


def test_score_counts_a_digression_as_an_extra_effective_word(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.99, par_length=1)
    chain.add_word("car")
    chain.add_word("dog")  # digression, per test above
    # effective_words = 2 played + 1 digression penalty: 2 over par.
    assert chain.score() == 80


def test_score_counts_a_hint_as_two_extra_effective_words(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", par_length=1)  # default threshold=0.7
    chain.use_hint()
    chain.use_hint()
    # no steps played, but effective_words = 2 hints * 2: 3 over par.
    assert chain.score() == 70


def test_par_length_round_trips_through_to_dict_and_from_dict(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", par_length=3)
    restored = Chain.from_dict(tiny_model, chain.to_dict())
    assert restored.par_length == 3


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
    # Hint point costs are tracked for display/history, but scoring uses the
    # existing two-effective-words-per-hint weighting. Estimated par at 0.7 is 17.
    assert chain.score() == round(100 * (1.20 ** 13))


def test_restart_resets_hint_state(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    chain.use_hint()
    chain.restart()
    assert chain.hints_used == 0
    assert chain.hint_cost_total == 0
    assert chain.next_hint_cost() == 5
