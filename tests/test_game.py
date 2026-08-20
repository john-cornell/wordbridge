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


def test_score_penalizes_length_and_digressions(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.99)
    chain.add_word("car")
    chain.add_word("dog")  # digression, per test above
    assert chain.score() == 100 - (10 * 2) - (5 * 1)


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
    chain.add_word("dog")  # target_similarity ~0.11 vs auto
    chain.add_word("cat")  # target_similarity 0.0 vs auto - lower, must not win out
    best = chain.best_step()
    assert best.word == "dog"
    assert best.target_similarity == pytest.approx(
        tiny_model.similarity("dog", "auto")
    )
