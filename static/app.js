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
const thresholdInput = document.getElementById("threshold-input");
const difficultyButtons = document.querySelectorAll(".difficulty-btn");

function applyThreshold(value) {
  thresholdSlider.value = value;
  thresholdInput.value = value;
  chainGraph.setThreshold(Number(value));
  for (const btn of difficultyButtons) {
    btn.classList.toggle("active", Number(btn.dataset.threshold) === Number(value));
  }
}

async function persistThreshold(value) {
  try {
    await postJSON("/api/game/threshold", { threshold: Number(value) });
  } catch (err) {
    statusEl.textContent = err.message;
  }
}

thresholdSlider.addEventListener("input", () => applyThreshold(thresholdSlider.value));
thresholdSlider.addEventListener("change", () => persistThreshold(thresholdSlider.value));

thresholdInput.addEventListener("input", () => {
  const value = Number(thresholdInput.value);
  if (Number.isNaN(value) || value < 0 || value > 1) return;
  applyThreshold(value);
});
thresholdInput.addEventListener("change", () => {
  const value = Number(thresholdInput.value);
  if (Number.isNaN(value) || value < 0 || value > 1) return;
  persistThreshold(value);
});

applyThreshold(thresholdSlider.value);

for (const btn of difficultyButtons) {
  btn.addEventListener("click", () => {
    const value = btn.dataset.threshold;
    applyThreshold(value);
    persistThreshold(value);
  });
}

function setDifficultyButtonsDisabled(disabled) {
  for (const btn of difficultyButtons) {
    btn.disabled = disabled;
  }
}

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

async function getJSON(url) {
  const response = await fetch(url);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

function applyMoveResult(data, messagePrefix) {
  chainGraph.addStep(data);
  scoreEl.textContent = `Score: ${data.score}`;
  thresholdSlider.disabled = true;
  thresholdInput.disabled = true;
  setDifficultyButtonsDisabled(true);

  if (data.won) {
    chainGraph.highlightWinningConnection(data.winning_connection);
    const path = data.winning_connection
      .map((link) => `${link.a} —${link.similarity.toFixed(2)}→ ${link.b}`)
      .join(" ");
    let message = `${messagePrefix || ""}You connected the words! ${path}`;
    if (!data.saved_to_high_scores) {
      message += " (Not saved to high scores — you gave up on this pair earlier.)";
    }
    statusEl.textContent = message;
    document.getElementById("word-input").disabled = true;
    document.getElementById("add-word-btn").disabled = true;
    document.getElementById("hint-btn").disabled = true;
    document.getElementById("give-up-btn").disabled = true;
    document.getElementById("restart-btn").hidden = true;
  } else if (data.over_soft_cap) {
    statusEl.textContent = `${messagePrefix || ""}Chain is getting long — score is dropping fast.`;
  } else {
    statusEl.textContent = messagePrefix || "";
  }
}

function showGame(startWord, targetWord, startTargetSimilarity, threshold) {
  startWordEl.textContent = startWord;
  targetWordEl.textContent = targetWord;
  chainGraph.reset(startWord, targetWord, startTargetSimilarity);
  scoreEl.textContent = "";
  statusEl.textContent = "";
  document.getElementById("word-input").disabled = false;
  document.getElementById("add-word-btn").disabled = false;
  document.getElementById("hint-btn").disabled = false;
  document.getElementById("give-up-btn").disabled = false;
  document.getElementById("restart-btn").hidden = false;
  setupSection.hidden = true;
  gameSection.hidden = false;

  if (typeof threshold === "number") {
    applyThreshold(threshold);
  }
  thresholdSlider.disabled = false;
  thresholdInput.disabled = false;
  setDifficultyButtonsDisabled(false);
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
    input.value = "";
    applyMoveResult(data);
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

document.getElementById("hint-btn").addEventListener("click", async () => {
  const btn = document.getElementById("hint-btn");

  let costData;
  try {
    costData = await getJSON("/api/game/hint_cost");
  } catch (err) {
    statusEl.textContent = err.message;
    return;
  }

  const proceed = confirm(`Use a hint for ${costData.cost} points? It'll be added to your chain automatically.`);
  if (!proceed) return;

  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Thinking…";
  try {
    const data = await postJSON("/api/game/hint");
    if (data.hint_word === null) {
      statusEl.textContent = "No hint available from here.";
      btn.disabled = false;
      return;
    }
    applyMoveResult(data, `Hint: '${data.hint_word}' (cost ${data.cost} points). `);
    if (!data.won) btn.disabled = false;
  } catch (err) {
    statusEl.textContent = err.message;
    btn.disabled = false;
  } finally {
    btn.textContent = originalText;
  }
});

document.getElementById("give-up-btn").addEventListener("click", async () => {
  const btn = document.getElementById("give-up-btn");
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Finding a route…";
  try {
    const data = await postJSON("/api/game/give_up");
    document.getElementById("word-input").disabled = true;
    document.getElementById("add-word-btn").disabled = true;
    document.getElementById("hint-btn").disabled = true;
    thresholdSlider.disabled = true;
    thresholdInput.disabled = true;
    setDifficultyButtonsDisabled(true);

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
    btn.disabled = false;
  } finally {
    btn.textContent = originalText;
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
