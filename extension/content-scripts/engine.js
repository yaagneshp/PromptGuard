// Generic prompt-submission capture engine.
//
// Rather than a bespoke DOM scraper per platform, this listens for the two
// near-universal submission triggers across LLM chat UIs (Enter-without-Shift,
// and a click on a button whose accessible name is "send"/"submit") and reads
// whichever textarea/contenteditable element is currently focused (or, for
// click submissions, the most recently non-empty composer on the page). This
// is deliberately resilient to markup/class-name churn on the target sites,
// at the cost of being less precise than a hand-tuned selector per platform.
// Per-platform overrides can be added to PLATFORM_MAP if the generic
// heuristic ever misses on a specific site.

(function () {
  if (window.__promptguardInjected) return;
  window.__promptguardInjected = true;

  const PLATFORM_MAP = [
    { match: /(^|\.)chatgpt\.com$|(^|\.)chat\.openai\.com$/, name: "chatgpt", display: "ChatGPT" },
    { match: /(^|\.)claude\.ai$/, name: "claude", display: "Claude" },
    { match: /(^|\.)gemini\.google\.com$/, name: "gemini", display: "Gemini" },
    { match: /(^|\.)copilot\.microsoft\.com$/, name: "copilot", display: "Copilot" },
    { match: /(^|\.)perplexity\.ai$/, name: "perplexity", display: "Perplexity" },
    { match: /(^|\.)chat\.deepseek\.com$/, name: "deepseek", display: "DeepSeek" },
    { match: /(^|\.)grok\.com$/, name: "grok", display: "Grok" },
    { match: /(^|\.)chat\.mistral\.ai$/, name: "mistral", display: "Mistral Le Chat" },
  ];

  function detectPlatform() {
    const host = location.hostname;
    const found = PLATFORM_MAP.find((p) => p.match.test(host));
    return found || { name: "unknown", display: host };
  }

  function isComposerElement(el) {
    if (!el || !el.getAttribute) return false;
    return (
      el.tagName === "TEXTAREA" ||
      el.getAttribute("contenteditable") === "true" ||
      el.getAttribute("role") === "textbox"
    );
  }

  function extractText(el) {
    if (el.tagName === "TEXTAREA") return el.value || "";
    return el.innerText !== undefined ? el.innerText : el.textContent || "";
  }

  function getComposerText() {
    const active = document.activeElement;
    if (isComposerElement(active)) return extractText(active);

    const candidates = Array.from(
      document.querySelectorAll('textarea, [contenteditable="true"], div[role="textbox"]')
    );
    const withText = candidates.filter((el) => extractText(el).trim().length > 0);
    return withText.length ? extractText(withText[withText.length - 1]) : "";
  }

  function isSendTrigger(target) {
    const btn = target.closest && target.closest('button, [role="button"], input[type="submit"]');
    if (!btn) return false;
    const label = (btn.getAttribute("aria-label") || btn.getAttribute("title") || btn.textContent || "").trim();
    return /\b(send|submit)\b/i.test(label) && label.length < 60;
  }

  let lastCapture = { key: null, time: 0 };
  function shouldEmit(text) {
    const now = Date.now();
    const key = text.length + ":" + text.slice(0, 50);
    if (lastCapture.key === key && now - lastCapture.time < 800) return false;
    lastCapture = { key, time: now };
    return true;
  }

  function emitSubmission(text) {
    const platform = detectPlatform();
    chrome.runtime.sendMessage({
      type: "PROMPT_SUBMITTED",
      platform: platform.name,
      text,
      occurred_at: new Date().toISOString(),
    });
  }

  function maybeCapture() {
    const text = getComposerText().trim();
    if (text && shouldEmit(text)) emitSubmission(text);
  }

  document.addEventListener(
    "keydown",
    (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) maybeCapture();
    },
    true
  );

  document.addEventListener(
    "click",
    (e) => {
      if (isSendTrigger(e.target)) maybeCapture();
    },
    true
  );
})();
