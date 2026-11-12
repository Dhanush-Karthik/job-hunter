import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { core, input, output, vendor } from "./common.mjs";

const data = await input();
if (data.submit !== false || data.headed !== true) throw new Error("Only headed, fill-only assistance is supported");
const { getProfilePath } = await core("path-resolver.mjs");
const { loadYaml } = await core("lib/yaml-document.mjs");
const { validateUrlSecurity } = await core("liveness-browser.mjs");
await validateUrlSecurity(data.url);
const profile = loadYaml(readFileSync(getProfilePath(process.cwd()), "utf8"));
// Same candidate-first identity precedence as prepare-application.mjs.
const person = { ...profile, ...(profile.candidate || {}) };
const fullName = person.name || person.full_name || "";
const words = fullName.trim().split(/\s+/);
const values = {
  first: person.first_name || words[0] || "", last: person.last_name || words.slice(1).join(" "),
  name: fullName, email: person.email, phone: person.phone, linkedin: person.linkedin,
  website: person.portfolio || person.website || person.portfolio_url,
};
const require = createRequire(path.join(vendor, "package.json"));
const { chromium } = require("playwright");
const browser = await chromium.launch({ headless: false });
const context = await browser.newContext();
// Guard the fill phase against implicit submissions and background application requests.
await context.route("**/*", async (route) => {
  if (!["GET", "HEAD", "OPTIONS"].includes(route.request().method())) return route.abort();
  return route.continue();
});
await context.addInitScript(() => {
  window.__jobhunterFilling = true;
  document.addEventListener("submit", (event) => {
    if (window.__jobhunterFilling) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
});
const page = await context.newPage();
await page.goto(data.url, { waitUntil: "domcontentloaded" });
const filled = [];
for (const frame of page.frames()) {
  const fields = frame.locator('input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="checkbox"]):not([type="radio"]), textarea');
  for (let i = 0; i < await fields.count(); i++) {
    const field = fields.nth(i);
    if (!await field.isVisible() || !await field.isEnabled() || !await field.isEditable()) continue;
    const info = await field.evaluate((el) => ({
      type: el.type, hint: [el.name, el.id, el.autocomplete, el.placeholder, el.getAttribute("aria-label"),
        ...Array.from(el.labels || [], (label) => label.textContent)].join(" ").toLowerCase(),
    }));
    if (info.type === "file") {
      if (data.pdf && /resume|\bcv\b/.test(info.hint)) {
        await field.setInputFiles(data.pdf);
        filled.push("Approved CV attachment");
      }
      continue;
    }
    let key;
    if (/first.?name|given.?name|given-name/.test(info.hint)) key = "first";
    else if (/last.?name|family.?name|surname|family-name/.test(info.hint)) key = "last";
    else if (/e.?mail/.test(info.hint)) key = "email";
    else if (/phone|mobile|\btel\b/.test(info.hint)) key = "phone";
    else if (/linkedin/.test(info.hint)) key = "linkedin";
    else if (/website|portfolio/.test(info.hint)) key = "website";
    else if (/full.?name|\bname\b/.test(info.hint)) key = "name";
    if (key && values[key] && !await field.inputValue()) {
      await field.fill(String(values[key]));
      filled.push(key);
    }
  }
}
// Hand over only after all automated actions stop. The owner can now review and submit manually.
await context.unroute("**/*");
for (const frame of page.frames()) await frame.evaluate(() => { window.__jobhunterFilling = false; });
output({ owner_browser_ready: true, filled, submitted: false });
await new Promise((resolve) => browser.on("disconnected", resolve));
