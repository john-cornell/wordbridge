const ANONYMOUS_FILTER_VALUE = "__anonymous__";
const MONTH_ABBREVIATIONS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatDate(isoString) {
  const date = new Date(isoString);
  const day = String(date.getDate()).padStart(2, "0");
  const month = MONTH_ABBREVIATIONS[date.getMonth()];
  const year = String(date.getFullYear()).slice(-2);
  return `${day}-${month}-${year}`;
}

const solutionGraph = new ChainGraph(
  document.getElementById("solution-graph"),
  document.getElementById("solution-tooltip")
);

let currentSolution = null; // { startWord, targetWord, startTargetSimilarity, threshold, steps, winningConnection }
let currentScores = [];

function filterValueFor(playerName) {
  return playerName || ANONYMOUS_FILTER_VALUE;
}

function populatePlayerFilter(scores) {
  const select = document.getElementById("player-filter");
  const previousValue = select.value;
  const names = new Map(); // filter value -> display label
  for (const entry of scores) {
    names.set(filterValueFor(entry.player_name), entry.player_name || "Anonymous");
  }

  select.innerHTML = "";
  const allOption = document.createElement("option");
  allOption.value = "";
  allOption.textContent = "All players";
  select.appendChild(allOption);

  for (const [value, label] of [...names.entries()].sort((a, b) => a[1].localeCompare(b[1]))) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.appendChild(option);
  }

  if (previousValue && names.has(previousValue)) {
    select.value = previousValue;
  }
}

function renderScoresTable() {
  const filterValue = document.getElementById("player-filter").value;
  const tbody = document.getElementById("scores-body");
  const emptyMessage = document.getElementById("empty-message");
  const filterEmptyMessage = document.getElementById("filter-empty-message");
  tbody.innerHTML = "";

  if (currentScores.length === 0) {
    emptyMessage.hidden = false;
    filterEmptyMessage.hidden = true;
    return;
  }
  emptyMessage.hidden = true;

  const visibleScores = filterValue
    ? currentScores.filter((entry) => filterValueFor(entry.player_name) === filterValue)
    : currentScores;

  filterEmptyMessage.hidden = visibleScores.length > 0;

  for (const entry of visibleScores) {
    const row = document.createElement("tr");

    const player = document.createElement("td");
    player.textContent = entry.player_name || "Anonymous";
    row.appendChild(player);

    const source = document.createElement("td");
    source.textContent = entry.start_word;
    row.appendChild(source);

    const destination = document.createElement("td");
    if (entry.has_solution) {
      const link = document.createElement("a");
      link.href = "#";
      link.className = "nav-link";
      link.textContent = entry.target_word;
      link.addEventListener("click", (evt) => {
        evt.preventDefault();
        openSolution(entry);
      });
      destination.appendChild(link);
    } else {
      destination.textContent = entry.target_word;
      destination.title = "No solution recorded for this attempt";
    }
    row.appendChild(destination);

    const score = document.createElement("td");
    score.textContent = entry.score;
    row.appendChild(score);

    const threshold = document.createElement("td");
    threshold.textContent = typeof entry.threshold === "number" ? entry.threshold.toFixed(2) : "";
    row.appendChild(threshold);

    const date = document.createElement("td");
    date.textContent = formatDate(entry.created_at);
    row.appendChild(date);

    tbody.appendChild(row);
  }
}

async function loadHighScores() {
  const response = await fetch("/api/high_scores");
  const data = await response.json();

  currentScores = data.scores;
  populatePlayerFilter(currentScores);
  renderScoresTable();
}

document.getElementById("player-filter").addEventListener("change", renderScoresTable);

document.getElementById("clear-scores-btn").addEventListener("click", async () => {
  if (!confirm("Clear all high scores? This can't be undone.")) return;
  const password = prompt("Password to clear high scores:");
  if (password === null) return;

  const response = await fetch("/api/high_scores/clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!response.ok) {
    alert("Wrong password.");
    return;
  }
  loadHighScores();
});

async function openSolution(entry) {
  const modal = document.getElementById("solution-modal");
  const errorEl = document.getElementById("solution-error");
  const graphEl = document.getElementById("solution-graph");
  errorEl.hidden = true;
  graphEl.hidden = false;
  modal.hidden = false;

  const response = await fetch(`/api/high_scores/${entry.id}/solution`);
  const data = response.ok ? await response.json() : null;
  if (!data || !data.available) {
    currentSolution = null;
    graphEl.hidden = true;
    errorEl.hidden = false;
    return;
  }

  currentSolution = {
    startWord: data.start_word,
    targetWord: data.target_word,
    startTargetSimilarity: data.start_target_similarity,
    threshold: data.threshold,
    steps: data.steps,
    winningConnection: data.winning_connection,
  };
  document.getElementById("solution-threshold").textContent =
    `Threshold: ${data.threshold.toFixed(2)}. Dashed purple border marks a hint.`;
  setSolutionView("direct");
}

function setSolutionView(view) {
  document.getElementById("solution-view-direct").classList.toggle("active", view === "direct");
  document.getElementById("solution-view-full").classList.toggle("active", view === "full");

  if (!currentSolution) return;

  solutionGraph.reset(currentSolution.startWord, currentSolution.targetWord, currentSolution.startTargetSimilarity);
  // Same threshold the game was actually played at, so non-bridge
  // connections among the tried words show up exactly like they did live -
  // not just the winning bridge.
  solutionGraph.setThreshold(currentSolution.threshold);

  if (view === "direct") {
    // Only the actual bridge the player made - not every word they tried.
    const path = [currentSolution.startWord, ...currentSolution.winningConnection.map((link) => link.b)];
    solutionGraph.showSuggestedRoute(path);
  } else {
    // Every word the player actually played, including digressions -
    // replayed exactly like live gameplay renders each step.
    for (const step of currentSolution.steps) {
      solutionGraph.addStep(step);
    }
    solutionGraph.highlightWinningConnection(currentSolution.winningConnection);
  }
}

document.getElementById("solution-view-direct").addEventListener("click", () => setSolutionView("direct"));
document.getElementById("solution-view-full").addEventListener("click", () => setSolutionView("full"));

document.getElementById("solution-modal-close").addEventListener("click", () => {
  document.getElementById("solution-modal").hidden = true;
  currentSolution = null;
});

loadHighScores();
