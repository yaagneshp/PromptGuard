const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ENGINE_SRC = fs.readFileSync(
  path.join(__dirname, "..", "content-scripts", "engine.js"),
  "utf8"
);

let passed = 0;
let failed = 0;

function assert(condition, message) {
  if (condition) {
    passed++;
  } else {
    failed++;
    console.error(`FAIL: ${message}`);
  }
}

function setup(html, hostname) {
  const dom = new JSDOM(html, { url: `https://${hostname}/`, runScripts: "outside-only" });
  const sent = [];
  dom.window.chrome = { runtime: { sendMessage: (msg) => sent.push(msg) } };
  dom.window.eval(ENGINE_SRC);
  return { dom, sent };
}

function enterKeydown(el, { shiftKey = false } = {}) {
  const event = new el.ownerDocument.defaultView.KeyboardEvent("keydown", {
    key: "Enter",
    shiftKey,
    bubbles: true,
    cancelable: true,
  });
  el.dispatchEvent(event);
}

function click(el) {
  const event = new el.ownerDocument.defaultView.MouseEvent("click", {
    bubbles: true,
    cancelable: true,
  });
  el.dispatchEvent(event);
}

// --- Test 1: textarea + Enter submit ---
{
  const { dom, sent } = setup(
    `<textarea id="composer"></textarea>`,
    "chatgpt.com"
  );
  const textarea = dom.window.document.getElementById("composer");
  textarea.value = "my email is bob@example.com";
  textarea.focus();
  enterKeydown(textarea);

  assert(sent.length === 1, `textarea+Enter should emit exactly one message, got ${sent.length}`);
  assert(sent[0]?.text === "my email is bob@example.com", "captured text should match textarea value");
  assert(sent[0]?.platform === "chatgpt", `platform should be 'chatgpt', got '${sent[0]?.platform}'`);
}

// --- Test 2: Shift+Enter must NOT submit (newline) ---
{
  const { dom, sent } = setup(`<textarea id="composer"></textarea>`, "claude.ai");
  const textarea = dom.window.document.getElementById("composer");
  textarea.value = "line one";
  textarea.focus();
  enterKeydown(textarea, { shiftKey: true });

  assert(sent.length === 0, `Shift+Enter should not emit, got ${sent.length}`);
}

// --- Test 3: contenteditable composer + Enter ---
{
  const { dom, sent } = setup(
    `<div contenteditable="true" id="composer">call me on 07911 123456</div>`,
    "gemini.google.com"
  );
  const div = dom.window.document.getElementById("composer");
  div.focus();
  enterKeydown(div);

  assert(sent.length === 1, `contenteditable+Enter should emit exactly one message, got ${sent.length}`);
  assert(sent[0]?.platform === "gemini", `platform should be 'gemini', got '${sent[0]?.platform}'`);
  assert(sent[0]?.text.includes("07911"), "captured text should include the phone number");
}

// --- Test 4: click on a Send button (icon-only button, aria-label on ancestor) ---
{
  const { dom, sent } = setup(
    `<textarea id="composer">AKIAIOSFODNN7EXAMPLE</textarea>
     <button aria-label="Send message"><svg id="icon"></svg></button>`,
    "copilot.microsoft.com"
  );
  const svgIcon = dom.window.document.getElementById("icon");
  click(svgIcon); // click lands on the icon, not the button itself

  assert(sent.length === 1, `click on send-button icon should emit exactly one message, got ${sent.length}`);
  assert(sent[0]?.platform === "copilot", `platform should be 'copilot', got '${sent[0]?.platform}'`);
}

// --- Test 5: click on an unrelated button must NOT submit ---
{
  const { dom, sent } = setup(
    `<textarea id="composer">hello</textarea>
     <button aria-label="New chat">New chat</button>`,
    "www.perplexity.ai"
  );
  const btn = dom.window.document.querySelector("button");
  click(btn);

  assert(sent.length === 0, `click on unrelated button should not emit, got ${sent.length}`);
}

// --- Test 6: empty composer must NOT submit ---
{
  const { dom, sent } = setup(`<textarea id="composer"></textarea>`, "chat.deepseek.com");
  const textarea = dom.window.document.getElementById("composer");
  textarea.value = "   ";
  textarea.focus();
  enterKeydown(textarea);

  assert(sent.length === 0, `empty/whitespace-only composer should not emit, got ${sent.length}`);
}

// --- Test 7: unknown platform falls back gracefully ---
{
  const { dom, sent } = setup(`<textarea id="composer"></textarea>`, "some-random-site.example");
  const textarea = dom.window.document.getElementById("composer");
  textarea.value = "test";
  textarea.focus();
  enterKeydown(textarea);

  assert(sent.length === 1, "unknown host should still emit (extension only injects on matched hosts anyway)");
  assert(sent[0]?.platform === "unknown", `platform should fall back to 'unknown', got '${sent[0]?.platform}'`);
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
