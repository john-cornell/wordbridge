import random
import re

_TOKEN_RE = re.compile(r"^[a-z]+$")


class WordVectorModel:
    """Wraps a gensim KeyedVectors instance with the operations Wordbridge needs."""

    def __init__(self, keyed_vectors, vocab_limit=50000):
        self._kv = keyed_vectors
        self._filtered_vocab = self._build_filtered_vocab(vocab_limit)

    def _build_filtered_vocab(self, vocab_limit):
        filtered = [word for word in self._kv.index_to_key if _TOKEN_RE.match(word)]
        return filtered[:vocab_limit]

    def contains(self, word):
        return word in self._kv

    def similarity(self, word_a, word_b):
        return float(self._kv.similarity(word_a, word_b))

    def random_pair(self, rng=random):
        word_a, word_b = rng.sample(self._filtered_vocab, 2)
        return word_a, word_b


def load_google_news_model(vocab_limit=50000):
    import gensim.downloader as api

    keyed_vectors = api.load("word2vec-google-news-300")
    return WordVectorModel(keyed_vectors, vocab_limit=vocab_limit)
