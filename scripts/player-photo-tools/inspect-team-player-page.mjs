import process from "node:process";

import { chromium } from "playwright-core";

const url = process.argv[2];
if (!url) throw new Error("Usage: node inspect-team-player-page.mjs <url>");

const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
const apiResponses = [];
const networkResponses = [];
page.on("response", async (response) => {
  const contentType = response.headers()["content-type"] ?? "";
  if (contentType.includes("json")) {
    networkResponses.push({ url: response.url(), status: response.status(), contentType });
  }
  if (!contentType.includes("json") || !/player|roster|squad|member/i.test(response.url())) return;
  try {
    apiResponses.push({ url: response.url(), status: response.status(), body: await response.json() });
  } catch {
    apiResponses.push({ url: response.url(), status: response.status(), body: null });
  }
});

try {
  await page.goto(url, { waitUntil: "networkidle", timeout: 45_000 });
  await page.waitForTimeout(2_000);
  const images = await page.locator("img").evaluateAll((nodes) =>
    nodes
      .map((image) => ({
        src: image.currentSrc || image.src,
        alt: image.alt,
        naturalWidth: image.naturalWidth,
        naturalHeight: image.naturalHeight,
        displayedWidth: image.getBoundingClientRect().width,
        displayedHeight: image.getBoundingClientRect().height,
      }))
      .filter(
        (image) =>
          !image.src.startsWith("data:") && (image.naturalWidth >= 200 || image.naturalHeight >= 200),
      ),
  );
  const links = await page.locator("a").evaluateAll((nodes) =>
    nodes
      .map((link) => ({
        text: (link.textContent || "").replace(/\s+/g, " ").trim(),
        href: link.href,
        onclick: link.getAttribute("onclick") || "",
      }))
      .filter((link) => link.href)
      .slice(0, 500),
  );
  process.stdout.write(
    `${JSON.stringify({ title: await page.title(), url: page.url(), links, images, apiResponses, networkResponses }, null, 2)}\n`,
  );
} finally {
  await browser.close();
}
