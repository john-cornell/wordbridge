import random

import numpy as np
from gensim.models import KeyedVectors

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


def test_random_pair_pool_size_restricts_sampling_to_the_first_n_words(tiny_model):
    # tiny_model._filtered_vocab is ["cat", "dog", "car", "auto"], in that
    # order. pool_size=2 must never draw "car" or "auto".
    for _ in range(20):
        word_a, word_b = tiny_model.random_pair(rng=random.Random(), pool_size=2, max_similarity=1.1)
        assert {word_a, word_b} == {"cat", "dog"}


def test_find_route_stops_once_the_deadline_passes():
    # A deadline already in the past must abort before the first hop's
    # (comparatively expensive) most_similar call, returning None rather
    # than doing any real search work.
    angles_deg = {"start": 0, "near": 18.1949, "far": 60, "target": 90}
    words = list(angles_deg.keys())
    vectors = np.array([[np.cos(np.radians(a)), np.sin(np.radians(a))] for a in angles_deg.values()])
    kv = KeyedVectors(vector_size=2)
    kv.add_vectors(words, vectors)
    model = WordVectorModel(kv, vocab_limit=10)

    import time

    route = model.find_route(
        "start", "target", max_hops=6, neighbors_per_hop=2, win_threshold=0.7, deadline=time.monotonic() - 1
    )

    assert route is None


def test_find_route_returns_direct_route_when_target_is_nearest_neighbor(tiny_model):
    route = tiny_model.find_route("cat", "dog")
    assert route == ["dog"]


def test_find_route_returns_none_when_no_route_found_within_hop_cap(tiny_model):
    route = tiny_model.find_route("cat", "auto", max_hops=1, neighbors_per_hop=1, win_threshold=2.0)
    assert route is None


def test_find_route_never_returns_an_excluded_word(tiny_model):
    # "dog" is cat's only real (above-threshold) connection in the tiny
    # fixture — cat-car and cat-auto are exactly 0 similarity. Excluding
    # dog must not fall back to a fake route through disconnected words
    # (the old rank-only bug would have); it must correctly report none.
    route = tiny_model.find_route("cat", "auto", exclude={"dog"})
    assert route is None


def test_find_route_only_hops_through_connections_that_clear_the_threshold():
    # "far" is much closer to the target than "near" is, but far is NOT
    # validly connected to "start" at this threshold (0.5 < 0.7) — only
    # rank-nearest, not threshold-connected. Picking it directly (as the
    # old rank-only logic did) would suggest a hop the graph itself would
    # never draw an edge for. The route must detour through "near" (which
    # IS validly connected to start) before reaching "far", and must
    # explicitly land on the literal target word at the end rather than
    # stopping one word short of it.
    angles_deg = {"start": 0, "near": 18.1949, "far": 60, "target": 90}
    words = list(angles_deg.keys())
    vectors = np.array([[np.cos(np.radians(a)), np.sin(np.radians(a))] for a in angles_deg.values()])
    kv = KeyedVectors(vector_size=2)
    kv.add_vectors(words, vectors)
    model = WordVectorModel(kv, vocab_limit=10)

    route = model.find_route("start", "target", max_hops=6, neighbors_per_hop=2, win_threshold=0.7)

    assert route == ["near", "far", "target"]


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
