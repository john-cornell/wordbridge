const ANONYMOUS_FILTER_VALUE = "__anonymous__";

const solutionGraph = new ChainGraph(
  document.getElementById("solution-graph"),
  document.getElementById("solution-tooltip")
);

let currentSolution = null; // { startWord, targetWord, solutionRoute, solutionTrace }
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
    destination.textContent = entry.target_word;
    row.appendChild(destination);

    const score = document.createElement("td");
    score.textContent = entry.score;
    row.appendChild(score);

    const date = document.createElement("td");
    date.textContent = new Date(entry.created_at).toLocaleString();
    row.appendChild(date);

    const actions = document.createElement("td");
    actions.classList.add("col-actions");
    const solutionBtn = document.createElement("button");
    solutionBtn.type = "button";
    solutionBtn.className = "btn btn-outline";
    solutionBtn.textContent = "Solution";
    if (!entry.has_solution) {
      solutionBtn.disabled = true;
      solutionBtn.title = "No solution recorded for this attempt";
    } else {
      solutionBtn.addEventListener("click", () => openSolution(entry));
    }
    actions.appendChild(solutionBtn);
    row.appendChild(actions);

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
  await fetch("/api/high_scores/clear", { method: "POST" });
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
  if (!response.ok) {
    currentSolution = null;
    graphEl.hidden = true;
    errorEl.hidden = false;
    return;
  }

  const data = await response.json();
  if (!data.solution_route) {
    currentSolution = null;
    graphEl.hidden = true;
    errorEl.hidden = false;
    return;
  }

  currentSolution = {
    startWord: entry.start_word,
    targetWord: entry.target_word,
    solutionRoute: data.solution_route,
    solutionTrace: data.solution_trace || [],
  };
  setSolutionView("direct");
}

function setSolutionView(view) {
  document.getElementById("solution-view-direct").classList.toggle("active", view === "direct");
  document.getElementById("solution-view-full").classList.toggle("active", view === "full");

  if (!currentSolution) return;

  if (view === "direct") {
    solutionGraph.reset(currentSolution.startWord, currentSolution.targetWord, null);
    solutionGraph.showSuggestedRoute(currentSolution.solutionRoute);
  } else {
    solutionGraph.renderSearchTrace(currentSolution.startWord, currentSolution.targetWord, currentSolution.solutionTrace);
  }
}

document.getElementById("solution-view-direct").addEventListener("click", () => setSolutionView("direct"));
document.getElementById("solution-view-full").addEventListener("click", () => setSolutionView("full"));

document.getElementById("solution-modal-close").addEventListener("click", () => {
  document.getElementById("solution-modal").hidden = true;
  currentSolution = null;
});

loadHighScores();
