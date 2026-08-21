import random

from wordbridge.model import WordVectorModel


def test_contains_known_word(tiny_model):
    assert tiny_model.contains("cat") is True


def test_contains_unknown_word(tiny_model):
    assert tiny_model.contains("nonexistent") is False


def test_similarity_close_words_higher_than_far_words(tiny_model):
    close = tiny_model.similarity("cat", "dog")
    far = tiny_model.similarity("cat", "car")
    assert close > far


def test_filtered_vocab_excludes_multi_word_and_capitalized(tiny_model):
    assert "multi_word" not in tiny_model._filtered_vocab
    assert "Capital" not in tiny_model._filtered_vocab
    assert "cat" in tiny_model._filtered_vocab


def test_random_pair_returns_two_distinct_filtered_words(tiny_model):
    word_a, word_b = tiny_model.random_pair(rng=random.Random(42))
    assert word_a != word_b
    assert word_a in tiny_model._filtered_vocab
    assert word_b in tiny_model._filtered_vocab


def test_random_pair_resamples_when_first_pick_is_already_too_similar(tiny_model):
    class FakeRng:
        def __init__(self, picks):
            self._picks = iter(picks)

        def sample(self, population, k):
            return list(next(self._picks))

    # car/auto are ~0.99 similar in the tiny fixture — already an instant win.
    # cat/car are ~0.0 similar — a safe, clearly-not-connected fallback pick.
    fake_rng = FakeRng([("car", "auto"), ("cat", "car")])
    word_a, word_b = tiny_model.random_pair(rng=fake_rng, max_similarity=0.7)
    assert (word_a, word_b) == ("cat", "car")


def test_find_route_returns_direct_route_when_target_is_nearest_neighbor(tiny_model):
    route = tiny_model.find_route("cat", "dog")
    assert route == ["dog"]


def test_find_route_returns_none_when_no_route_found_within_hop_cap(tiny_model):
    route = tiny_model.find_route("cat", "auto", max_hops=1, neighbors_per_hop=1, win_threshold=2.0)
    assert route is None


def test_find_route_never_returns_an_excluded_word(tiny_model):
    # "dog" is cat's literal nearest neighbor and would normally be the
    # answer — excluding it forces the search to find a real alternative.
    route = tiny_model.find_route("cat", "auto", exclude={"dog"})
    assert "dog" not in route


def test_find_route_does_not_use_the_destination_shortcut_when_destination_excluded(tiny_model):
    # Normally "auto" (the literal target) is found directly in cat's
    # neighbors and returned immediately. Excluding it must block that.
    route = tiny_model.find_route("cat", "auto", exclude={"auto"})
    assert route is None or "auto" not in route


def test_find_route_refuses_a_candidate_that_is_not_an_improvement(tiny_model):
    # "car" is already ~0.99 similar to "auto". With "auto" itself excluded,
    # the only other real candidates ("cat", "dog") are far worse matches.
    # Even though a low win_threshold would technically be satisfied by one
    # of them, the search must not wander backwards to reach it.
    route = tiny_model.find_route("car", "auto", exclude={"auto"}, win_threshold=0.05)
    assert route is None
