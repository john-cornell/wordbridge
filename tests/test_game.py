import pytest

from wordbridge.game import Chain


def test_add_word_computes_similarities(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.99)
    step = chain.add_word("dog")
    assert step.word == "dog"
    assert step.neighbor_similarity == pytest.approx(tiny_model.similarity("dog", "cat"))
    assert step.target_similarity == pytest.approx(tiny_model.similarity("dog", "auto"))


def test_add_word_rejects_word_not_connected_to_previous(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    with pytest.raises(ValueError):
        chain.add_word("car")  # cat and car are unrelated (sim ~0.0) in the tiny fixture


def test_digression_detected_when_target_similarity_drops(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.6)
    chain.add_word("dog")  # connected to cat; still far from target
    chain.add_word("van")  # connected to dog; much closer to target
    step = chain.add_word("cat")  # connected to van; further from target than van was -> digression
    assert step.is_digression is True


def test_add_word_rejects_unknown_word(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    with pytest.raises(ValueError):
        chain.add_word("nonexistent")


def test_is_won_when_target_similarity_meets_threshold(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.6)
    assert chain.is_won() is False
    chain.add_word("dog")  # connected, but still far from target
    assert chain.is_won() is False
    chain.add_word("van")  # connected to dog, and close enough to target
    assert chain.is_won() is True


def test_score_penalizes_length_and_digressions(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.6)
    chain.add_word("dog")
    chain.add_word("van")
    chain.add_word("cat")  # digression, per test above
    assert chain.score() == 100 - (10 * 3) - (5 * 1)


def test_is_over_soft_cap(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", soft_cap=1, threshold=0)
    chain.add_word("car")
    assert chain.is_over_soft_cap() is False
    chain.add_word("dog")
    assert chain.is_over_soft_cap() is True


def test_restart_clears_steps(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0)
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
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0)
    chain.add_word("car")
    chain.mark_completed()

    restored = Chain.from_dict(tiny_model, chain.to_dict())

    assert restored.completed is True


def test_not_completed_round_trips_through_to_dict_and_from_dict(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0)
    chain.add_word("car")

    restored = Chain.from_dict(tiny_model, chain.to_dict())

    assert restored.completed is False


def test_restart_resets_completed_flag(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    chain.mark_completed()
    chain.restart()
    assert chain.completed is False


def test_add_word_records_similarities_to_every_other_word(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.6)
    chain.add_word("dog")
    step = chain.add_word("van")

    similarities_by_word = {entry["word"]: entry["similarity"] for entry in step.similarities}
    assert similarities_by_word["cat"] == pytest.approx(tiny_model.similarity("van", "cat"))
    assert similarities_by_word["auto"] == pytest.approx(tiny_model.similarity("van", "auto"))
    assert similarities_by_word["dog"] == pytest.approx(tiny_model.similarity("van", "dog"))
    assert len(step.similarities) == 3


def test_first_word_similarities_cover_only_start_and_target(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    step = chain.add_word("dog")
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
