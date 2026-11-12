// Bridge policy only: provider implementations stay in the untouched vendor tree.
const india = /\b(india|chennai|madras|bengaluru|bangalore|hyderabad|secunderabad|pune|mumbai|bombay|delhi|ncr|gurgaon|gurugram|noida|kochi|cochin|coimbatore|kolkata|calcutta|ahmedabad|gandhinagar|jaipur|chandigarh|mohali|indore|bhopal|nagpur|nashik|surat|vadodara|rajkot|lucknow|kanpur|patna|ranchi|bhubaneswar|bhubaneshwar|visakhapatnam|vizag|vijayawada|mysore|mysuru|mangalore|mangaluru|trivandrum|thiruvananthapuram|thrissur|kozhikode|calicut|madurai|trichy|tiruchirappalli|salem|tiruppur|vellore|tirunelveli|pondicherry|puducherry|guwahati|shillong|dehradun|raipur|jamshedpur|udaipur|jodhpur|karnataka|tamil nadu|telangana|andhra pradesh|kerala|maharashtra|gujarat|rajasthan|punjab|haryana|uttar pradesh|madhya pradesh|west bengal|odisha|orissa|bihar|jharkhand|chhattisgarh|uttarakhand|uttaranchal|himachal pradesh|jammu|kashmir|ladakh|assam|arunachal pradesh|manipur|meghalaya|mizoram|nagaland|sikkim|tripura|goa|andaman|nicobar|lakshadweep|dadra|nagar haveli|daman|diu)\b/i;
const remote = /\b(remote|anywhere|worldwide|world wide|global|apac|asia|wfh|work from home)\b/i;
const unknown = /^(unknown|unspecified|not specified|not available|n a|none|null|tbd|multiple locations?|various locations?|location flexible|flexible|other|other locations?)$/i;

export function keepLocation(location) {
  // Preserve unfamiliar representations for the downstream audit.
  if (typeof location !== "string") return true;
  const text = location.replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  return !text || unknown.test(text) || india.test(text) || remote.test(text);
}

export function positiveEnv(env, name, fallback, max = 2_147_483.647) {
  const value = Number(env[name]);
  return Number.isFinite(value) && value > 0 && value <= max ? value : fallback;
}

export async function scanTargets(targets, {
  resolve, makeCtx, applyResponseCap, applyTimeout, withScope,
  concurrency = 8, entryTimeoutS = 60, deadlineS = 1200, log = console.error,
}) {
  const postings = [], errors = [], sources = {};
  const remoteBoards = new Set(["remotive", "weworkremotely", "himalayas", "remoteok"]);
  const states = targets.map(entry => ({ entry, providerId: entry.provider, status: "pending" }));
  let successes = 0, cursor = 0, stopped = false, deadlineTimer;
  function fail(state, reason) {
    if (state.status === "success" || state.status === "error") return;
    state.status = "error";
    errors.push(`${state.entry.name}: ${reason}`);
    if (remoteBoards.has(state.providerId)) sources[state.providerId] = { count: 0, error: reason };
    log(errors.at(-1));
  }
  async function fetchEntry(state) {
    state.status = "running";
    let timer;
    const controller = new AbortController();
    state.controller = controller;
    try {
      const resolved = resolve(state.entry);
      if (!resolved?.provider) throw new Error(resolved?.error || "no public API provider");
      const provider = resolved.provider;
      state.providerId = provider.id;
      const ctx = { ...makeCtx(), includeUndated: true, signal: controller.signal };
      applyResponseCap(ctx, state.entry);
      // timeout_ms bounds requests; the race bounds the whole tenant, including
      // providers that do not consult ctx or its signal.
      const requested = state.entry.timeout_ms;
      const timeoutMs = Math.min(
        Number.isInteger(requested) && requested > 0 ? requested : Infinity,
        entryTimeoutS * 1000,
      );
      applyTimeout(ctx, { ...state.entry, timeout_ms: Math.max(1, Math.floor(timeoutMs)) });
      const expired = new Promise((_, reject) => {
        timer = setTimeout(() => {
          const error = new Error(`timeout after ${entryTimeoutS}s`);
          reject(error);
          controller.abort(error);
        }, entryTimeoutS * 1000);
      });
      // The vendor scope cancels HTTP retries and destroys each tenant's sockets
      // even when its fetch keeps doing background work after the race ends.
      const jobs = await withScope(() => Promise.race([
        Promise.resolve().then(() => provider.fetch(state.entry, ctx)), expired,
      ]), { signal: controller.signal });
      if (stopped || state.status !== "running") return;
      if (!Array.isArray(jobs)) throw new Error("provider returned no posting array");
      const kept = jobs.filter(job => keepLocation(job.location));
      const normalized = kept.map(job => ({ ...job, company: job.company || state.entry.name, provider: provider.id }));
      postings.push(...normalized);
      state.status = "success";
      successes++;
      if (remoteBoards.has(provider.id)) sources[provider.id] = { count: kept.length, error: null };
      log(`${state.entry.name}: ${jobs.length} fetched, ${kept.length} kept (${provider.id})`);
    } catch (error) {
      if (!stopped) fail(state, error?.message || String(error));
    } finally {
      clearTimeout(timer);
    }
  }
  async function worker() {
    while (!stopped && cursor < states.length) await fetchEntry(states[cursor++]);
  }
  const deadline = new Promise(resolve => {
    deadlineTimer = setTimeout(() => {
      stopped = true;
      for (const state of states) {
        if (state.status === "pending" || state.status === "running") {
          fail(state, "deadline");
          state.controller?.abort(new Error("deadline"));
        }
      }
      resolve();
    }, deadlineS * 1000);
  });
  try {
    await Promise.race([
      Promise.all(Array.from({ length: Math.min(concurrency, targets.length) }, worker)),
      deadline,
    ]);
  } finally {
    stopped = true;
    clearTimeout(deadlineTimer);
  }
  if (!successes) throw new Error(errors.at(-1) || "No enabled scan targets");
  return { postings, errors, sources };
}
