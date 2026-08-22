from dataclasses import dataclass, field


@dataclass
class Step:
    word: str
    neighbor_similarity: float
    target_similarity: float
    is_digression: bool
    similarities: list = field(default_factory=list)


class Chain:
    def __init__(self, model, start_word, target_word, threshold=0.7, soft_cap=15, par_length=None, solution_route=None):
        self._model = model
        self.start_word = start_word
        self.target_word = target_word
        self.threshold = threshold
        self.soft_cap = soft_cap
        self.par_length = par_length
        self.solution_route = solution_route
        self.steps = []
        self.completed = False
        self.won = False
        self.gave_up_before = False
        self.hints_used = 0
        self.hint_cost_total = 0

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

        other_words = [self.start_word, self.target_word] + [s.word for s in self.steps]
        similarities = [
            {"word": other, "similarity": self._model.similarity(word, other)}
            for other in other_words
        ]

        step = Step(word, neighbor_similarity, target_similarity, is_digression, similarities)
        self.steps.append(step)
        return step

    def start_target_similarity(self):
        return self._model.similarity(self.start_word, self.target_word)

    def best_step(self):
        if not self.steps:
            return None
        return max(self.steps, key=lambda step: step.target_similarity)

    def is_won(self):
        return self._connection_path() is not None

    def winning_connection(self):
        path = self._connection_path()
        if path is None:
            return None
        return [
            {
                "a": path[i],
                "b": path[i + 1],
                "similarity": self._model.similarity(path[i], path[i + 1]),
            }
            for i in range(len(path) - 1)
        ]

    def _known_words(self):
        return [self.start_word, self.target_word] + [s.word for s in self.steps]

    def _build_adjacency(self, words):
        adjacency = {word: set() for word in words}
        for i, a in enumerate(words):
            for b in words[i + 1:]:
                if a != b and self._model.similarity(a, b) >= self.threshold:
                    adjacency[a].add(b)
                    adjacency[b].add(a)
        return adjacency

    def _connection_path(self):
        if not self.steps:
            return None

        words = self._known_words()
        adjacency = self._build_adjacency(words)

        visited = {self.start_word}
        parent = {}
        frontier = [self.start_word]
        while frontier:
            word = frontier.pop(0)
            if word == self.target_word:
                path = [word]
                while path[-1] != self.start_word:
                    path.append(parent[path[-1]])
                path.reverse()
                return path
            for neighbor in adjacency[word] - visited:
                visited.add(neighbor)
                parent[neighbor] = word
                frontier.append(neighbor)
        return None

    def _components(self):
        """Group start/target/played words into connected components at the current threshold."""
        words = self._known_words()
        adjacency = self._build_adjacency(words)

        seen = set()
        components = []
        for word in words:
            if word in seen:
                continue
            component = set()
            frontier = [word]
            while frontier:
                current = frontier.pop()
                if current in component:
                    continue
                component.add(current)
                frontier.extend(adjacency[current] - component)
            seen |= component
            components.append(component)
        return components

    def closest_unconnected_pair(self):
        """Find the most promising bridge: the highest-similarity pair of known
        words spanning the start's component or the target's component to
        anything outside it. Returns (anchor, other)."""
        components = self._components()
        start_component = next(c for c in components if self.start_word in c)
        target_component = next(c for c in components if self.target_word in c)
        all_words = self._known_words()

        best_pair = None
        best_similarity = None
        for anchor_component in (start_component, target_component):
            for anchor in anchor_component:
                for other in all_words:
                    if other in anchor_component:
                        continue
                    similarity = self._model.similarity(anchor, other)
                    if best_similarity is None or similarity > best_similarity:
                        best_similarity = similarity
                        best_pair = (anchor, other)
        return best_pair

    def is_over_soft_cap(self):
        return len(self.steps) > self.soft_cap

    def num_digressions(self):
        return sum(1 for step in self.steps if step.is_digression)

    def score(self):
        if self.par_length is None:
            # No par could be established for this puzzle (e.g. the model
            # couldn't find any route within search limits) — fall back to
            # the old absolute formula rather than leave the game unscored.
            raw = 100 - (10 * len(self.steps)) - (5 * self.num_digressions()) - self.hint_cost_total
            difficulty_multiplier = self.threshold / 0.5
            return round(raw * difficulty_multiplier)

        # Par-relative scoring: a digression still counts as a played word,
        # plus a 1-word penalty for the detour; a hint costs 2 effective
        # words since it's a bigger crutch than just wandering off-path.
        effective_words = len(self.steps) + self.num_digressions() + (2 * self.hints_used)
        if effective_words <= 0:
            return 100
        return min(100, round(100 * self.par_length / effective_words))

    def next_hint_cost(self):
        return 5 * (2 ** self.hints_used)

    def use_hint(self):
        cost = self.next_hint_cost()
        self.hints_used += 1
        self.hint_cost_total += cost
        return cost

    def restart(self):
        self.steps = []
        self.completed = False
        self.won = False
        self.hints_used = 0
        self.hint_cost_total = 0

    def mark_completed(self):
        self.completed = True

    def mark_won(self):
        self.completed = True
        self.won = True

    def mark_given_up(self):
        self.completed = True
        self.gave_up_before = True

    def to_dict(self):
        return {
            "start_word": self.start_word,
            "target_word": self.target_word,
            "threshold": self.threshold,
            "soft_cap": self.soft_cap,
            "completed": self.completed,
            "won": self.won,
            "gave_up_before": self.gave_up_before,
            "hints_used": self.hints_used,
            "hint_cost_total": self.hint_cost_total,
            "par_length": self.par_length,
            "solution_route": self.solution_route,
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
            par_length=data.get("par_length"),
            solution_route=data.get("solution_route"),
        )
        chain.steps = [Step(**step) for step in data["steps"]]
        chain.completed = data.get("completed", False)
        chain.won = data.get("won", False)
        chain.gave_up_before = data.get("gave_up_before", False)
        chain.hints_used = data.get("hints_used", 0)
        chain.hint_cost_total = data.get("hint_cost_total", 0)
        return chain
