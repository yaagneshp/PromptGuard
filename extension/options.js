const DEFAULT_CONFIG = {
  backendUrl: "http://127.0.0.1:8000",
  apiKey: "change-me-dev-key",
};

async function load() {
  const stored = await chrome.storage.sync.get(DEFAULT_CONFIG);
  document.getElementById("backendUrl").value = stored.backendUrl;
  document.getElementById("apiKey").value = stored.apiKey;
}

async function save() {
  const backendUrl = document.getElementById("backendUrl").value.trim() || DEFAULT_CONFIG.backendUrl;
  const apiKey = document.getElementById("apiKey").value.trim() || DEFAULT_CONFIG.apiKey;
  await chrome.storage.sync.set({ backendUrl, apiKey });
  const status = document.getElementById("status");
  status.textContent = "Saved.";
  setTimeout(() => (status.textContent = ""), 1500);
}

document.addEventListener("DOMContentLoaded", load);
document.getElementById("save")?.addEventListener("click", save);
