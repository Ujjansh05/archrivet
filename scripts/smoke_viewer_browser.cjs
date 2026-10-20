/* Optional developer smoke test. Requires an installed Playwright-compatible
   browser/runtime; neither is part of the viewer's production dependencies. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const { spawn } = require("node:child_process");
const { chromium } = require(process.env.ARCHRIVET_PLAYWRIGHT || "playwright");

(async () => {
  const root = path.resolve(__dirname, "..");
  const out = path.join(root, ".runtime", "viewer-browser");
  fs.mkdirSync(out, { recursive: true });
  const driver = spawn(process.env.ARCHRIVET_TEST_PYTHON || "python", [path.join(root, "tests", "viewer_browser_driver.py")], {
    cwd: root, windowsHide: true, env: { ...process.env, PYTHONPATH: path.join(root, "src") },
    stdio: ["pipe", "pipe", "inherit"],
  });
  const lines = readline.createInterface({ input: driver.stdout })[Symbol.asyncIterator]();
  async function read() {
    const result = await lines.next();
    assert(!result.done, "Viewer driver stopped before replying");
    return JSON.parse(result.value);
  }
  async function command(value) { driver.stdin.write(JSON.stringify(value) + "\n"); return read(); }
  let browser;
  try {
    const initial = await read();
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    const remoteRequests = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => { if (message.type() === "error" && /Content Security|Refused to/.test(message.text())) errors.push(message.text()); });
    let polls = 0;
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.protocol === "http:" && url.hostname !== "127.0.0.1") remoteRequests.push(url.origin);
      if (url.protocol === "https:") remoteRequests.push(url.origin);
      if (url.pathname === "/api/state") polls += 1;
    });
    await page.goto(initial.url);
    await page.waitForFunction(() => document.querySelector("#revision-value").textContent === "1");
    assert.equal(await page.locator(".graph-node").count(), 3);
    await command({ action: "update", example: 1 });
    await page.waitForFunction(() => document.querySelector("#revision-value").textContent === "2");
    assert.equal(await page.locator(".graph-node").count(), 4);
    await page.locator('[data-node-id="cache"]').click();
    assert.match(await page.locator("#selection-detail").textContent(), /Missing detail/);
    assert.match(await page.locator("#changes-list").textContent(), /Price cache/);
    await page.screenshot({ path: path.join(out, "live-cache.png"), fullPage: true });
    await page.locator("#zoom-in").click();
    await page.locator("#fit-view").click();
    await page.locator("#close-view").click();
    assert(await page.locator("#closed-state").isVisible());
    const before = polls;
    await command({ action: "update", example: 2 });
    // Deliberately wait across two poll intervals: a paused view must stay quiet.
    await new Promise((resolve) => setTimeout(resolve, 2200));
    assert.equal(polls, before, "Closing must stop browser polling");
    assert.equal(await page.locator("#revision-value").textContent(), "2");
    await page.locator("#reopen-view").click();
    await page.waitForFunction(() => document.querySelector("#revision-value").textContent === "3");
    await command({ action: "close" });
    await page.waitForFunction(() => !document.querySelector("#closed-state").hidden);
    await command({ action: "open" });
    await page.waitForFunction(() => document.querySelector("#closed-state").hidden);
    const download = page.waitForEvent("download");
    await page.locator("#download-json").click();
    const exportPath = path.join(out, "export.json");
    await (await download).saveAs(exportPath);
    const exported = fs.readFileSync(exportPath, "utf8");
    assert.equal(JSON.parse(exported).revision, 3);
    assert(!exported.includes("token="));
    await page.setViewportSize({ width: 390, height: 850 });
    await page.waitForFunction(() => {
      const stage = document.querySelector("#canvas-stage").getBoundingClientRect();
      return [...document.querySelectorAll(".graph-node")].every((node) => {
        const rect = node.getBoundingClientRect();
        return rect.left >= stage.left && rect.right <= stage.right && rect.top >= stage.top && rect.bottom <= stage.bottom;
      });
    });
    await page.screenshot({ path: path.join(out, "mobile.png"), fullPage: true });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.setViewportSize({ width: 300, height: 850 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.setViewportSize({ width: 1440, height: 1000 });
    await command({ action: "update", diagram: {
      title: 'Cycle <img src=x onerror="window.injected=1">',
      nodes: [{ id: "a", label: "<script>window.injected=1</script>" }, { id: "b", label: "Worker" }],
      edges: [{ id: "ab", source: "a", target: "b", label: "request" }, { id: "ba", source: "b", target: "a", label: "retry" }, { id: "aa", source: "a", target: "a", label: "self" }],
    } });
    await page.waitForFunction(() => document.querySelector("#revision-value").textContent === "4");
    assert.equal(await page.locator(".graph-edge").count(), 3);
    assert.equal(await page.evaluate(() => window.injected), undefined);
    assert.equal(await page.locator("img").count(), 0);
    await page.locator('[data-node-id="b"]').focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.locator("#selection-label").textContent(), "Worker");
    await page.screenshot({ path: path.join(out, "cycle.png"), fullPage: true });
    const svgDownload = page.waitForEvent("download");
    await page.locator("#download-svg").click();
    const svgPath = path.join(out, "export.svg");
    await (await svgDownload).saveAs(svgPath);
    const svg = fs.readFileSync(svgPath, "utf8");
    assert(svg.includes("&lt;script&gt;"));
    assert(!svg.includes("<script>"));
    driver.stdin.write('{"action":"shutdown"}\n');
    driver.stdin.end();
    await page.waitForFunction(() => !document.querySelector("#offline-banner").hidden, { timeout: 10000 });
    assert.deepEqual(errors, []);
    assert.deepEqual(remoteRequests, []);
    fs.writeFileSync(path.join(out, "report.json"), JSON.stringify({ passed: true, browser: "Chromium headless", cases: ["render", "live update", "changes", "details", "zoom", "close stops polling", "reopen latest", "server close/reopen same revision", "JSON export", "mobile", "cycles", "markup displayed as text", "keyboard", "SVG export", "offline", "no remote requests"], model_loaded: false, real_ai_host: false }, null, 2));
    console.log("Browser smoke passed: live updates, close/reopen, exports, narrow screen, cycles, safe text and offline state.");
  } finally {
    driver.stdin.end();
    if (browser) await browser.close();
    if (driver.exitCode === null) driver.kill();
  }
})().catch((error) => { console.error(error.message); process.exitCode = 1; });
