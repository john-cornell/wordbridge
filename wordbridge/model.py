import random
import re
import time

from gensim.models import KeyedVectors

_TOKEN_RE = re.compile(r"^[a-z]+$")


class WordVectorModel:
    """Wraps a gensim KeyedVectors instance with the operations Wordbridge needs."""

    def __init__(self, keyed_vectors, vocab_limit=200000):
        filtered_words = [word for word in keyed_vectors.index_to_key if _TOKEN_RE.match(word)][:vocab_limit]

        # Rebuild as a real, much smaller KeyedVectors instead of just
        # filtering a Python list — vocab_limit previously only trimmed
        # candidate selection while the full multi-million-word matrix (plus
        # a same-sized normalized copy gensim lazily builds on the first
        # similarity/most_similar call) stayed resident regardless. That
        # combination OOM-killed an 8GB production VPS on its first real
        # game. This cuts actual memory from ~7GB to well under 1GB by
        # never holding more vectors than the app can ever use.
        #
        # Index the underlying array directly rather than keyed_vectors[words]
        # — that goes through gensim's __getitem__, which does one Python-level
        # get_vector() call per word. At 200k+ words that's ~170 SECONDS of
        # pure interpreter overhead (confirmed: consistent gunicorn worker
        # startup timeouts in production, every single boot). A single
        # vectorized numpy index is milliseconds regardless of vocab size.
        indices = [keyed_vectors.key_to_index[word] for word in filtered_words]
        small_kv = KeyedVectors(vector_size=keyed_vectors.vector_size)
        small_kv.add_vectors(filtered_words, keyed_vectors.vectors[indices])

        self._kv = small_kv
        self._filtered_vocab = filtered_words
        self._filtered_vocab_set = set(filtered_words)

    def vocab_size(self):
        return len(self._filtered_vocab)

    def contains(self, word):
        return word in self._kv

    def similarity(self, word_a, word_b):
        return float(self._kv.similarity(word_a, word_b))

    def random_pair(self, rng=random, max_similarity=0.7, max_attempts=20, pool_size=None):
        # index_to_key (and so _filtered_vocab, which preserves its order) is
        # frequency-ranked, most common first. Widening vocab_limit to give
        # hints/manual-mode/search more words to work with also widens random
        # pair selection into much rarer words by default — rare words have
        # sparse, poorly-connected neighborhoods, which is what made most
        # random games fail to find any route at all once vocab_limit grew
        # past ~100k. pool_size lets callers keep pair selection in the
        # dense, well-connected common-word range regardless of vocab_limit.
        pool = self._filtered_vocab[:pool_size] if pool_size else self._filtered_vocab
        for _ in range(max_attempts):
            word_a, word_b = rng.sample(pool, 2)
            if self.similarity(word_a, word_b) < max_similarity:
                return word_a, word_b
        return word_a, word_b

    def find_route(
        self,
        from_word,
        to_word,
        max_hops=6,
        neighbors_per_hop=20,
        win_threshold=0.7,
        exclude=frozenset(),
        deadline=None,
    ):
        current = from_word
        current_similarity = self._kv.similarity(current, to_word)
        if to_word not in exclude and current_similarity >= win_threshold:
            return [to_word]

        visited = {from_word} | set(exclude)
        path = []
        for _ in range(max_hops):
            # Checked before paying for the (comparatively expensive)
            # most_similar call below — real per-call cost varies a lot by
            # hardware, so this is the actual mechanism that keeps a single
            # search call bounded, not just an attempt count.
            if deadline is not None and time.monotonic() >= deadline:
                return None

            neighbors = [word for word, _ in self._kv.most_similar(current, topn=neighbors_per_hop)]

            # A candidate must actually clear win_threshold against the word
            # we're hopping FROM — matching the same threshold the graph
            # itself uses to draw an edge. Being one of current's nearest
            # neighbors by rank doesn't imply that; picking on rank alone
            # produced routes the graph would never actually connect.
            candidates = [
                w
                for w in neighbors
                if w in self._filtered_vocab_set
                and w not in visited
                and self._kv.similarity(current, w) >= win_threshold
            ]
            if not candidates:
                return None

            best = max(candidates, key=lambda w: self._kv.similarity(w, to_word))
            best_similarity = self._kv.similarity(best, to_word)
            if best_similarity <= current_similarity:
                # Nothing reachable from here is any closer than we already
                # are — stop rather than wander sideways through a cluster
                # of near-synonyms or drift backwards.
                return None

            path.append(best)
            if best == to_word or best_similarity >= win_threshold:
                # Reaching threshold-similarity to the target counts as a
                # win even if `best` isn't literally the target word — make
                # that explicit in the returned path instead of stopping one
                # word short of the word the player was actually aiming for.
                if best != to_word:
                    path.append(to_word)
                return path

            visited.add(best)
            current = best
            current_similarity = best_similarity
        return None


def load_google_news_model(vocab_limit=200000):
    import gensim.downloader as api

    # Load with a hard cap instead of api.load()'s default (which parses
    # and materializes the FULL ~3-million-word file, only for nearly all
    # of it to become garbage the instant WordVectorModel builds its own
    # smaller copy). Freeing millions of individual Python objects (dict
    # entries, strings) is real, unpredictable work - confirmed hanging a
    # production gunicorn worker for minutes on every single boot, well
    # past its own request-serving timeout.
    #
    # The multiplier covers what _TOKEN_RE filters out (phrases, capitalized
    # entries). Measured in production: a 3x buffer only yielded ~13.6% of
    # raw entries as valid (81,705 words from 600,000 raw), well short of
    # vocab_limit - not the ~33% originally guessed. 8.5x is sized off that
    # real number (200,000 / 0.136 ≈ 1.47M, +~15% margin) rather than
    # another guess. Re-tune from the actual logged vocab_size if it's
    # still short, or vocab_limit changes.
    path = api.load("word2vec-google-news-300", return_path=True)
    keyed_vectors = KeyedVectors.load_word2vec_format(path, binary=True, limit=int(vocab_limit * 8.5))
    return WordVectorModel(keyed_vectors, vocab_limit=vocab_limit)
