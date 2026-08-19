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


def test_find_route_returns_direct_route_when_target_is_nearest_neighbor(tiny_model):
    route = tiny_model.find_route("cat", "dog")
    assert route == ["dog"]


def test_find_route_returns_none_when_no_route_found_within_hop_cap(tiny_model):
    route = tiny_model.find_route("cat", "auto", max_hops=1, neighbors_per_hop=1, win_threshold=2.0)
    assert route is None
