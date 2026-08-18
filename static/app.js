const setupSection = document.getElementById("setup");
const gameSection = document.getElementById("game");
const startWordEl = document.getElementById("start-word");
const targetWordEl = document.getElementById("target-word");
const chainList = document.getElementById("chain-list");
const scoreEl = document.getElementById("score");
const statusEl = document.getElementById("status");

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

function showGame(startWord, targetWord) {
  startWordEl.textContent = startWord;
  targetWordEl.textContent = targetWord;
  chainList.innerHTML = "";
  scoreEl.textContent = "";
  statusEl.textContent = "";
  setupSection.hidden = true;
  gameSection.hidden = false;
}

document.getElementById("random-btn").addEventListener("click", async () => {
  try {
    const data = await postJSON("/api/game/new", { mode: "random" });
    showGame(data.start_word, data.target_word);
  } catch (err) {
    statusEl.textContent = err.message;
  }
});

document.getElementById("manual-btn").addEventListener("click", async () => {
  const word1 = document.getElementById("word1-input").value.trim();
  const word2 = document.getElementById("word2-input").value.trim();
  try {
    const data = await postJSON("/api/game/new", { mode: "manual", word1, word2 });
    showGame(data.start_word, data.target_word);
  } catch (err) {
    statusEl.textContent = err.message;
  }
});

document.getElementById("add-word-btn").addEventListener("click", async () => {
  const input = document.getElementById("word-input");
  const word = input.value.trim();
  try {
    const data = await postJSON("/api/game/word", { word });
    const li = document.createElement("li");
    li.textContent = `${data.word} (neighbor: ${data.neighbor_similarity.toFixed(2)}, target: ${data.target_similarity.toFixed(2)})${data.is_digression ? " ⚠ digression" : ""}`;
    chainList.appendChild(li);
    scoreEl.textContent = `Score: ${data.score}`;
    input.value = "";

    if (data.won) {
      statusEl.textContent = "You connected the words!";
    } else if (data.over_soft_cap) {
      statusEl.textContent = "Chain is getting long — score is dropping fast.";
    } else {
      statusEl.textContent = "";
    }
  } catch (err) {
    statusEl.textContent = err.message;
  }
});

document.getElementById("restart-btn").addEventListener("click", async () => {
  try {
    const data = await postJSON("/api/game/restart");
    showGame(data.start_word, data.target_word);
  } catch (err) {
    statusEl.textContent = err.message;
  }
});
