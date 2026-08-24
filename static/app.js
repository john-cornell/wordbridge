const setupSection = document.getElementById("setup");
const gameSection = document.getElementById("game");
const startWordEl = document.getElementById("start-word");
const targetWordEl = document.getElementById("target-word");
const scoreEl = document.getElementById("score");
const parInfoEl = document.getElementById("par-info");
const statusEl = document.getElementById("status");
const setupStatusEl = document.getElementById("setup-status");
const fireworksOverlay = document.getElementById("fireworks-overlay");

const fireworks = new Fireworks.default(fireworksOverlay, {
  autoresize: true,
  opacity: 0.5,
  acceleration: 1.05,
  friction: 0.97,
  gravity: 1.5,
  particles: 40,
  traceLength: 3,
  traceSpeed: 10,
  explosion: 5,
  intensity: 20,
  flickering: 50,
});

let fireworksTimeout;

function showFireworks() {
  clearTimeout(fireworksTimeout);

  fireworks.start();

  fireworksTimeout = setTimeout(() => {
    fireworks.stop(true);
  }, 10000);
}

function stopFireworks() {
  clearTimeout(fireworksTimeout);
  fireworks.stop(true);
}

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

function formatParInfo(parLength, startTargetSimilarity, threshold) {
  if (typeof parLength === "number") {
    if (parLength === 1 && startTargetSimilarity >= threshold) {
      // The direct start->target similarity already clears the threshold,
      // so literally any word the player adds wins instantly - not a real
      // puzzle at this difficulty.
      return "These words are already connected at this threshold - any word you add will win instantly. Try a harder setting?";
    }
    return `Shortest path I found: ${parLength} word${parLength === 1 ? "" : "s"} (maybe you can do better!)`;
  }
  // par_length is null when the solver couldn't find any route at this
  // threshold within its search limits - that's a limit of the search,
  // not proof no connection exists.
  return "I couldn't find a path, but that doesn't mean there isn't one. Can you do better than me?";
}

async function persistThreshold(value) {
  try {
    const data = await postJSON("/api/game/threshold", { threshold: Number(value) });
    parInfoEl.textContent = formatParInfo(data.par_length, data.start_target_similarity, data.threshold);
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

async function parseJSONResponse(response) {
  let data;
  try {
    data = await response.json();
  } catch {
    // The server (or a proxy in front of it) returned something that
    // isn't JSON - e.g. nginx's own HTML error page during a brief
    // upstream restart. Surface a readable message instead of the raw
    // parse error.
    throw new Error(`Server error (${response.status}). Please try again.`);
  }
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return parseJSONResponse(response);
}

async function getJSON(url) {
  const response = await fetch(url);
  return parseJSONResponse(response);
}

const playerNameInput = document.getElementById("player-name-input");

async function loadPlayerName() {
  try {
    const data = await getJSON("/api/player_name");
    playerNameInput.value = data.name || "";
  } catch (err) {
    // Non-fatal — just leave the field blank if this fails.
  }
}

playerNameInput.addEventListener("change", async () => {
  try {
    await postJSON("/api/player_name", { name: playerNameInput.value.trim() });
  } catch (err) {
    statusEl.textContent = err.message;
  }
});

loadPlayerName();

function formatScoreLine(data) {
  if (typeof data.par_length === "number") {
    return `Score: ${data.score} (par ${data.par_length} · you: ${data.words_used} word${data.words_used === 1 ? "" : "s"})`;
  }
  return `Score: ${data.score}`;
}

function applyMoveResult(data, messagePrefix) {
  chainGraph.addStep(data);
  scoreEl.textContent = formatScoreLine(data);
  thresholdSlider.disabled = true;
  thresholdInput.disabled = true;
  setDifficultyButtonsDisabled(true);

  if (data.won) {
    showFireworks();
    chainGraph.highlightWinningConnection(data.winning_connection);
    const path = data.winning_connection
      .map((link) => `${link.a} —${link.similarity.toFixed(2)}→ ${link.b}`)
      .join(" ");
    let message = `${messagePrefix || ""}You connected the words! ${path}`;
    if (!data.saved_to_high_scores) {
      message += " (Not saved to high scores: you gave up on this pair earlier.)";
    }
    statusEl.textContent = message;
    document.getElementById("word-input").disabled = true;
    document.getElementById("add-word-btn").disabled = true;
    document.getElementById("hint-btn").disabled = true;
    document.getElementById("give-up-btn").disabled = true;
    document.getElementById("restart-btn").hidden = true;
  } else if (data.over_soft_cap) {
    statusEl.textContent = `${messagePrefix || ""}Chain is getting long. Score is dropping fast.`;
  } else {
    statusEl.textContent = messagePrefix || "";
  }
}

function showGame(startWord, targetWord, startTargetSimilarity, threshold, parLength) {
  startWordEl.textContent = startWord;
  targetWordEl.textContent = targetWord;
  chainGraph.reset(startWord, targetWord, startTargetSimilarity);
  scoreEl.textContent = "";
  parInfoEl.textContent = formatParInfo(parLength, startTargetSimilarity, threshold);
  statusEl.textContent = "";
  setupStatusEl.textContent = "";
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
  setupStatusEl.textContent = "";
  try {
    const data = await postJSON("/api/game/new", { mode: "random" });
    showGame(data.start_word, data.target_word, data.start_target_similarity, data.threshold, data.par_length);
  } catch (err) {
    setupStatusEl.textContent = err.message;
  }
});

document.getElementById("manual-btn").addEventListener("click", async () => {
  setupStatusEl.textContent = "";
  const word1 = document.getElementById("word1-input").value.trim();
  const word2 = document.getElementById("word2-input").value.trim();
  try {
    const data = await postJSON("/api/game/new", { mode: "manual", word1, word2 });
    showGame(data.start_word, data.target_word, data.start_target_similarity, data.threshold, data.par_length);
  } catch (err) {
    setupStatusEl.textContent = err.message;
  }
});

let addWordInFlight = false;

async function addWord() {
  // Prevent duplicate submissions while an add-word request is in progress.
  if (addWordInFlight) return;

  const input = document.getElementById("word-input");
  const btn = document.getElementById("add-word-btn");
  const word = input.value.trim();
  input.value = "";

  addWordInFlight = true;
  input.disabled = true;
  btn.disabled = true;
  try {
    const data = await postJSON("/api/game/word", { word });
    applyMoveResult(data);
    if (!data.won) {
      input.disabled = false;
      btn.disabled = false;
      input.focus();
    }
  } catch (err) {
    statusEl.textContent = err.message;
    input.disabled = false;
    btn.disabled = false;
  } finally {
    addWordInFlight = false;
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
      chainGraph.showSuggestedRoute(data.route);
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
    showGame(data.start_word, data.target_word, data.start_target_similarity, data.threshold, data.par_length);
  } catch (err) {
    statusEl.textContent = err.message;
  }
});

document.getElementById("new-game-btn").addEventListener("click", () => {
  stopFireworks();

  document.getElementById("word1-input").value = "";
  document.getElementById("word2-input").value = "";
  setupStatusEl.textContent = "";
  setupSection.hidden = false;
  gameSection.hidden = true;
});
