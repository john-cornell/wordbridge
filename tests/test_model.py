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
