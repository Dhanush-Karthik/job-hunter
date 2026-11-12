// Offline provider used by the real bridge scan entry point in subprocess tests.
export async function loadProviders() { return []; }
export function resolveProvider(entry) {
  if (entry.provider === "websearch") return { error: "no public API provider" };
  return { provider: {
    id: entry.provider || "fake",
    async fetch(target, ctx) {
      if (!ctx.signal || !ctx.timeoutMs) throw new Error("missing entry timeout context");
      console.error(`start:${target.name}`);
      ctx.signal.addEventListener("abort", () => console.error(`abort:${target.name}`), { once: true });
      if (target.hang) {
        // Deliberately ignore cancellation and keep Node alive. The bridge must
        // still flush its result and terminate at its deadline.
        setInterval(() => {}, 1000);
        return new Promise(() => {});
      }
      if (target.delayMs) await new Promise(resolve => setTimeout(resolve, target.delayMs));
      if (target.error) throw new Error(target.error);
      return target.jobs || [{ title: "Java Engineer", url: `https://jobs.test/${target.name}`, location: "Chennai" }];
    },
  } };
}
