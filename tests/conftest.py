import numpy as np
import pytest
from gensim.models import KeyedVectors

from wordbridge import create_app
from wordbridge.model import WordVectorModel


@pytest.fixture
def app():
    return create_app()


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
