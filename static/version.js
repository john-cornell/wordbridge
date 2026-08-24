(async function () {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    const el = document.getElementById("version-info");
    if (el && data.version) {
      el.textContent = `v${data.version}`;
    }
  } catch (err) {
    // Non-fatal - just leave the footer blank if this fails.
  }
})();
