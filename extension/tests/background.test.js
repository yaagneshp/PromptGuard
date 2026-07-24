// Exercises background.js's onMessage handler against the REAL running
// backend (http://127.0.0.1:8000) using a mock chrome.* API. Run the backend
// first: `uvicorn app.main:app` from backend/.

const fs = require("fs");
const path = require("path");

let passed = 0;
let failed = 0;
function assert(condition, message) {
  if (condition) passed++;
  else {
    failed++;
    console.error(`FAIL: ${message}`);
  }
}

const storageSync = { backendUrl: "http://127.0.0.1:8000", apiKey: "change-me-dev-key" };
const storageLocal = {};

global.chrome = {
  storage: {
    sync: { get: async (defaults) => ({ ...defaults, ...storageSync }) },
    local: {
      get: async (key) => ({ [key]: storageLocal[key] }),
      set: async (obj) => Object.assign(storageLocal, obj),
    },
  },
  runtime: { onMessage: { addListener: (fn) => (global.__listener = fn) } },
};

const BG_SRC = fs.readFileSync(path.join(__dirname, "..", "background.js"), "utf8");
eval(BG_SRC);

async function main() {
  const message = {
    type: "PROMPT_SUBMITTED",
    platform: "chatgpt",
    text: "My AWS key is AKIAIOSFODNN7EXAMPLE and card number is 4532015112830366",
    occurred_at: new Date().toISOString(),
  };

  const response = await new Promise((resolve) => {
    const keepAlive = global.__listener(message, {}, resolve);
    assert(keepAlive === true, "listener should return true to keep sendResponse channel open");
  });

  assert(response.ok === true, `expected ok response, got ${JSON.stringify(response)}`);
  assert(
    ["high", "critical"].includes(response.riskLevel),
    `expected high/critical risk for AWS key + credit card (35+30=65), got '${response.riskLevel}'`
  );
  assert(!!storageLocal.externalUserId, "background should generate and persist a pseudonymous externalUserId");
  assert(storageLocal.lastResult?.ok === true, "lastResult should be recorded for the popup to read");

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error("Test run crashed - is the backend running on 127.0.0.1:8000?", err);
  process.exit(1);
});
