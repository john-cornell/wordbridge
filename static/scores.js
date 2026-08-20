async function loadHighScores() {
  const response = await fetch("/api/high_scores");
  const data = await response.json();

  const tbody = document.getElementById("scores-body");
  const emptyMessage = document.getElementById("empty-message");

  if (data.scores.length === 0) {
    emptyMessage.hidden = false;
    return;
  }

  for (const entry of data.scores) {
    const row = document.createElement("tr");

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

    tbody.appendChild(row);
  }
}

loadHighScores();
