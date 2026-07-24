async function render() {
  const { lastResult } = await chrome.storage.local.get("lastResult");
  const el = document.getElementById("last");
  if (!lastResult) return;

  if (lastResult.ok) {
    el.className = "ok";
    el.textContent = `Last capture: ${lastResult.platform} — risk: ${lastResult.riskLevel} (${lastResult.at})`;
  } else {
    el.className = "fail";
    el.textContent = `Last capture failed on ${lastResult.platform}: ${lastResult.error || lastResult.status} (${lastResult.at})`;
  }
}

document.addEventListener("DOMContentLoaded", render);
