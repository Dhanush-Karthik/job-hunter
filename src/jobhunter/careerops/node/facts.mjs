import { readFileSync } from "node:fs";
import { core, input, output } from "./common.mjs";

const { document, source } = await input();
const { verifyFacts } = await core("verify-cv-facts.mjs");
const result = verifyFacts(readFileSync(document, "utf8"), { sourcePaths: [source] });
output({ ...result, ok: result.verdict === "pass" || result.verdict === "warn" });
