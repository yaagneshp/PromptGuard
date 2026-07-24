const DEFAULT_CONFIG = {
  backendUrl: "http://127.0.0.1:8000",
  apiKey: "change-me-dev-key",
};

async function getConfig() {
  const stored = await chrome.storage.sync.get(DEFAULT_CONFIG);
  return { ...DEFAULT_CONFIG, ...stored };
}

async function getExternalUserId() {
  const { externalUserId } = await chrome.storage.local.get("externalUserId");
  if (externalUserId) return externalUserId;
  const id = crypto.randomUUID();
  await chrome.storage.local.set({ externalUserId: id });
  return id;
}

async function recordLastResult(result) {
  await chrome.storage.local.set({ lastResult: { ...result, at: new Date().toISOString() } });
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type !== "PROMPT_SUBMITTED") return;

  (async () => {
    try {
      const config = await getConfig();
      const externalUserId = await getExternalUserId();
      const res = await fetch(`${config.backendUrl}/events/ingest`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": config.apiKey,
        },
        body: JSON.stringify({
          external_user_id: externalUserId,
          platform: message.platform,
          text: message.text,
          occurred_at: message.occurred_at,
        }),
      });

      const data = await res.json().catch(() => null);
      if (!res.ok) {
        await recordLastResult({ ok: false, platform: message.platform, status: res.status });
        sendResponse({ ok: false, status: res.status });
        return;
      }

      await recordLastResult({
        ok: true,
        platform: message.platform,
        riskLevel: data?.risk_score?.risk_level,
      });
      sendResponse({ ok: true, riskLevel: data?.risk_score?.risk_level });
    } catch (err) {
      await recordLastResult({ ok: false, platform: message.platform, error: String(err) });
      sendResponse({ ok: false, error: String(err) });
    }
  })();

  return true;
});
