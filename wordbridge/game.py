from dataclasses import dataclass


@dataclass
class Step:
    word: str
    neighbor_similarity: float
    target_similarity: float
    is_digression: bool


class Chain:
    def __init__(self, model, start_word, target_word, threshold=0.7, soft_cap=15):
        self._model = model
        self.start_word = start_word
        self.target_word = target_word
        self.threshold = threshold
        self.soft_cap = soft_cap
        self.steps = []
        self.completed = False

    def add_word(self, word):
        if not self._model.contains(word):
            raise ValueError(f"'{word}' is not a recognized word")

        previous_word = self.steps[-1].word if self.steps else self.start_word
        previous_target_similarity = (
            self.steps[-1].target_similarity
            if self.steps
            else self._model.similarity(self.start_word, self.target_word)
        )

        neighbor_similarity = self._model.similarity(word, previous_word)
        target_similarity = self._model.similarity(word, self.target_word)
        is_digression = target_similarity < previous_target_similarity

        step = Step(word, neighbor_similarity, target_similarity, is_digression)
        self.steps.append(step)
        return step

    def is_won(self):
        return bool(self.steps) and self.steps[-1].target_similarity >= self.threshold

    def is_over_soft_cap(self):
        return len(self.steps) > self.soft_cap

    def num_digressions(self):
        return sum(1 for step in self.steps if step.is_digression)

    def score(self):
        return 100 - (10 * len(self.steps)) - (5 * self.num_digressions())

    def restart(self):
        self.steps = []
        self.completed = False

    def mark_completed(self):
        self.completed = True

    def to_dict(self):
        return {
            "start_word": self.start_word,
            "target_word": self.target_word,
            "threshold": self.threshold,
            "soft_cap": self.soft_cap,
            "completed": self.completed,
            "steps": [
                {
                    "word": step.word,
                    "neighbor_similarity": step.neighbor_similarity,
                    "target_similarity": step.target_similarity,
                    "is_digression": step.is_digression,
                }
                for step in self.steps
            ],
        }

    @classmethod
    def from_dict(cls, model, data):
        chain = cls(
            model,
            start_word=data["start_word"],
            target_word=data["target_word"],
            threshold=data["threshold"],
            soft_cap=data["soft_cap"],
        )
        chain.steps = [Step(**step) for step in data["steps"]]
        chain.completed = data.get("completed", False)
        return chain
