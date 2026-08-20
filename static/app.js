const setupSection = document.getElementById("setup");
const gameSection = document.getElementById("game");
const startWordEl = document.getElementById("start-word");
const targetWordEl = document.getElementById("target-word");
const scoreEl = document.getElementById("score");
const statusEl = document.getElementById("status");

const chainGraph = new ChainGraph(
  document.getElementById("chain-graph"),
  document.getElementById("graph-tooltip")
);

const thresholdSlider = document.getElementById("threshold-slider");
const thresholdValueEl = document.getElementById("threshold-value");

function applyThreshold() {
  const value = Number(thresholdSlider.value);
  thresholdValueEl.textContent = value.toFixed(2);
  chainGraph.setThreshold(value);
}

thresholdSlider.addEventListener("input", applyThreshold);
thresholdSlider.addEventListener("change", async () => {
  try {
    await postJSON("/api/game/threshold", { threshold: Number(thresholdSlider.value) });
  } catch (err) {
    statusEl.textContent = err.message;
  }
});
applyThreshold();

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

function showGame(startWord, targetWord, startTargetSimilarity, threshold) {
  startWordEl.textContent = startWord;
  targetWordEl.textContent = targetWord;
  chainGraph.reset(startWord, targetWord, startTargetSimilarity);
  scoreEl.textContent = "";
  statusEl.textContent = "";
  document.getElementById("word-input").disabled = false;
  document.getElementById("add-word-btn").disabled = false;
  setupSection.hidden = true;
  gameSection.hidden = false;

  if (typeof threshold === "number") {
    thresholdSlider.value = threshold;
    applyThreshold();
  }
  thresholdSlider.disabled = false;
}

document.getElementById("random-btn").addEventListener("click", async () => {
  try {
    const data = await postJSON("/api/game/new", { mode: "random" });
    showGame(data.start_word, data.target_word, data.start_target_similarity, data.threshold);
  } catch (err) {
    statusEl.textContent = err.message;
  }
});

document.getElementById("manual-btn").addEventListener("click", async () => {
  const word1 = document.getElementById("word1-input").value.trim();
  const word2 = document.getElementById("word2-input").value.trim();
  try {
    const data = await postJSON("/api/game/new", { mode: "manual", word1, word2 });
    showGame(data.start_word, data.target_word, data.start_target_similarity, data.threshold);
  } catch (err) {
    statusEl.textContent = err.message;
  }
});

async function addWord() {
  const input = document.getElementById("word-input");
  const word = input.value.trim();
  try {
    const data = await postJSON("/api/game/word", { word });
    chainGraph.addStep(data);
    scoreEl.textContent = `Score: ${data.score}`;
    input.value = "";
    thresholdSlider.disabled = true;

    if (data.won) {
      chainGraph.highlightWinningConnection(data.winning_connection);
      const path = data.winning_connection
        .map((link) => `${link.a} —${link.similarity.toFixed(2)}→ ${link.b}`)
        .join(" ");
      statusEl.textContent = `You connected the words! ${path}`;
      document.getElementById("word-input").disabled = true;
      document.getElementById("add-word-btn").disabled = true;
    } else if (data.over_soft_cap) {
      statusEl.textContent = "Chain is getting long — score is dropping fast.";
    } else {
      statusEl.textContent = "";
    }
  } catch (err) {
    statusEl.textContent = err.message;
  }
}

document.getElementById("add-word-btn").addEventListener("click", addWord);

document.getElementById("word-input").addEventListener("keydown", (evt) => {
  if (evt.key === "Enter") {
    evt.preventDefault();
    addWord();
  }
});

document.getElementById("give-up-btn").addEventListener("click", async () => {
  try {
    const data = await postJSON("/api/game/give_up");
    document.getElementById("word-input").disabled = true;
    document.getElementById("add-word-btn").disabled = true;
    thresholdSlider.disabled = true;

    let message;
    if (data.best_word === null) {
      message = "You gave up without trying any words.";
    } else {
      message = `You gave up. Your best was '${data.best_word}' at ${data.best_similarity.toFixed(2)} similarity to the target.`;
    }
    if (data.route) {
      message += ` A possible route: ${data.route.join(" → ")}.`;
    }
    statusEl.textContent = message;
  } catch (err) {
    statusEl.textContent = err.message;
  }
});

document.getElementById("restart-btn").addEventListener("click", async () => {
  try {
    const data = await postJSON("/api/game/restart");
    showGame(data.start_word, data.target_word, data.start_target_similarity, data.threshold);
  } catch (err) {
    statusEl.textContent = err.message;
  }
});

document.getElementById("new-game-btn").addEventListener("click", () => {
  setupSection.hidden = false;
  gameSection.hidden = true;
});
