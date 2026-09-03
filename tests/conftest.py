import itertools
import string

import numpy as np
import pytest
from gensim.models import KeyedVectors

from wordbridge import create_app
from wordbridge.model import WordVectorModel


@pytest.fixture
def app(tiny_model):
    return create_app(vector_model=tiny_model, db_path=":memory:", secret_key="test-secret")


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def tiny_model():
    kv = KeyedVectors(vector_size=3)
    words = ["cat", "dog", "car", "auto", "multi_word", "Capital"]
    vectors = np.array([
        [1.0, 0.0, 0.0],   # cat
        [0.9, 0.1, 0.0],   # dog - close to cat
        [0.0, 1.0, 0.0],   # car
        [0.0, 0.9, 0.1],   # auto - close to car
        [0.5, 0.5, 0.5],   # multi_word - should be filtered (underscore)
        [0.2, 0.2, 0.2],   # Capital - should be filtered (not lowercase-alpha)
    ])
    kv.add_vectors(words, vectors)
    return WordVectorModel(kv, vocab_limit=10)


@pytest.fixture
def big_vocab_model():
    # Mutually-orthogonal one-hot vectors: every pair of distinct words has
    # similarity 0.0, so none of them can accidentally win or repeat-trigger
    # a digression. Gives enough genuinely distinct words to build a long
    # chain without ever needing to replay one.
    filler_words = [
        "".join(letters)
        for letters in itertools.islice(itertools.product(string.ascii_lowercase, repeat=3), 205)
    ]
    words = ["cat", "auto"] + filler_words
    vectors = np.eye(len(words))

    kv = KeyedVectors(vector_size=len(words))
    kv.add_vectors(words, vectors)
    return WordVectorModel(kv, vocab_limit=len(words))


@pytest.fixture
def big_vocab_app(big_vocab_model):
    return create_app(vector_model=big_vocab_model, db_path=":memory:", secret_key="test-secret")


@pytest.fixture
def big_vocab_client(big_vocab_app):
    return big_vocab_app.test_client()


@pytest.fixture
def hint_chain_model():
    # tiny_model's 4 real words don't leave room for a hint that bridges
    # without immediately winning (there's only one word left to suggest).
    # This fixture adds two intermediate words so a real hint sequence needs
    # two hints: the first ("bridge") joins the start's side without
    # reaching the target, the second ("gamma") completes the connection.
    kv = KeyedVectors(vector_size=4)
    words = ["alpha", "beta", "bridge", "gamma", "delta"]
    vectors = np.array([
        [1.0, 0.0, 0.0, 0.0],      # alpha (start)
        [0.95, 0.1, 0.0, 0.015],   # beta - close to alpha, played manually first
        [0.85, 0.3, 0.1, 0.035],   # bridge - close to beta, still below win_threshold to delta
        [0.0, 0.1, 0.3, 0.85],     # gamma - weakly close to bridge, close to delta
        [0.0, 0.0, 0.0, 1.0],      # delta (target)
    ])
    kv.add_vectors(words, vectors)
    return WordVectorModel(kv, vocab_limit=10)


@pytest.fixture
def hint_chain_app(hint_chain_model):
    return create_app(vector_model=hint_chain_model, db_path=":memory:", secret_key="test-secret")


@pytest.fixture
def hint_chain_client(hint_chain_app):
    return hint_chain_app.test_client()
