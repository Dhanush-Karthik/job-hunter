import { readFileSync } from "node:fs";
import path from "node:path";
import { core, input, output, vendor } from "./common.mjs";

await input();
const { loadYaml } = await core("lib/yaml-document.mjs");
const { loadProviders, resolveProvider } = await core("providers/_registry.mjs");
const { makeHttpCtx } = await core("providers/_http.mjs");
const { parallelFetch, applyEntryResponseCap } = await core("scan.mjs");
const { applyEntryTimeout } = await core("lib/entry-timeout.mjs");
const config = loadYaml(readFileSync(path.join(process.cwd(), "portals.yml"), "utf8"));
const providers = await loadProviders(path.join(vendor, "providers"));
const targets = [...(config.tracked_companies || []), ...(config.job_boards || [])]
  .filter((entry) => entry.enabled !== false);
const postings = [];
const errors = [];
const sources = {};
const remoteBoards = new Set(["remotive", "weworkremotely", "himalayas", "remoteok"]);
let successes = 0;
// Use the scanner's providers and bounded concurrency, then let jobhunter's auditable pipeline filter.
await parallelFetch(targets.map((entry) => async () => {
  let providerId = entry.provider;
  try {
    const resolved = resolveProvider(entry, providers, { skipIds: ["local-parser"] });
    if (!resolved?.provider) throw new Error(resolved?.error || "no public API provider");
    const provider = resolved.provider;
    providerId = provider.id;
    const ctx = { ...makeHttpCtx(), includeUndated: true };
    applyEntryResponseCap(ctx, entry);
    applyEntryTimeout(ctx, entry);
    const jobs = await provider.fetch(entry, ctx);
    if (!Array.isArray(jobs)) throw new Error("provider returned no posting array");
    successes++;
    if (remoteBoards.has(providerId)) sources[providerId] = { count: jobs.length, error: null };
    for (const job of jobs) postings.push({ ...job, company: job.company || entry.name, provider: provider.id });
    console.error(`${entry.name}: ${jobs.length} postings (${provider.id})`);
  } catch (error) {
    if (remoteBoards.has(providerId)) sources[providerId] = { count: 0, error: error.message };
    errors.push(`${entry.name}: ${error.message}`);
    console.error(errors.at(-1));
  }
}), 4);
if (!successes) throw new Error(errors.at(-1) || "No enabled scan targets");
output({ postings, errors, sources });
