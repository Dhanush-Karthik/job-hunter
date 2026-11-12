import { createRequire } from "node:module";
import path from "node:path";
import { core, input, output, vendor } from "./common.mjs";

const { url } = await input();
const { validateUrlSecurity, newLivenessPage, checkUrlLivenessWithFallback, createHeadedPageProvider } =
  await core("liveness-browser.mjs");
const { checkLivenessViaApi } = await core("liveness-api.mjs");
const { isClosureEvidence } = await core("liveness-core.mjs");
await validateUrlSecurity(url);
let verdict = await checkLivenessViaApi(url);
if (!verdict || !["active", "expired"].includes(verdict.result)) {
  const require = createRequire(path.join(vendor, "package.json"));
  const { chromium } = require("playwright");
  const browser = await chromium.launch({ headless: true });
  const headed = createHeadedPageProvider(chromium);
  try {
    const page = await newLivenessPage(browser);
    const { robotsAllows } = await core("robots-check.mjs");
    verdict = await checkUrlLivenessWithFallback(page, url, { getHeadedPage: headed.get, robotsGate: robotsAllows });
  } finally {
    await browser.close();
    await headed.close();
  }
}
output({ ...verdict, is_live: verdict?.result === "active" ? true : isClosureEvidence(verdict) ? false : null });
