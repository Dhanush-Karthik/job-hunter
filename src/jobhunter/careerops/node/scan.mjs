import { readFileSync } from "node:fs";
import path from "node:path";
import { core, input, vendor } from "./common.mjs";
import { positiveEnv, scanTargets } from "./scan-controls.mjs";

await input();
const { loadYaml } = await core("lib/yaml-document.mjs");
const { loadProviders, resolveProvider } = await core("providers/_registry.mjs");
const { makeHttpCtx } = await core("providers/_http.mjs");
const { withConnectionScope } = await core("providers/_connection-scope.mjs");
const { applyEntryResponseCap } = await core("lib/entry-response-cap.mjs");
const { applyEntryTimeout } = await core("lib/entry-timeout.mjs");
const config = loadYaml(readFileSync(path.join(process.cwd(), "portals.yml"), "utf8"));
const providers = await loadProviders(path.join(vendor, "providers"));
const targets = [...(config.tracked_companies || []), ...(config.job_boards || [])]
  .filter(entry => entry.enabled !== false);
const started = Date.now();
const result = await scanTargets(targets, {
  resolve: entry => resolveProvider(entry, providers, { skipIds: ["local-parser"] }),
  makeCtx: makeHttpCtx, applyResponseCap: applyEntryResponseCap,
  applyTimeout: applyEntryTimeout, withScope: withConnectionScope,
  concurrency: Math.max(1, Math.floor(positiveEnv(process.env, "JOBHUNTER_SCAN_CONCURRENCY", 8, 1024))),
  entryTimeoutS: positiveEnv(process.env, "JOBHUNTER_SCAN_ENTRY_TIMEOUT_S", 60),
  deadlineS: positiveEnv(process.env, "JOBHUNTER_SCAN_DEADLINE_S", 1200),
});
console.error(`Scan finished in ${((Date.now() - started) / 1000).toFixed(1)}s: ${result.postings.length} postings, ${result.errors.length} errors`);
// Flush the result first: providers ignoring cancellation must not hold the
// command open with their own sockets, retries or timers.
process.stdout.write(JSON.stringify(result) + "\n", () => process.exit(0));
