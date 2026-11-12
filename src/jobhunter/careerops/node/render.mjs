import { readFileSync } from "node:fs";
import path from "node:path";
import { core, input } from "./common.mjs";

const data = await input();
const { parseCvEnvelope } = await core("web/src/lib/cv-envelope.mjs");
const {
  renderHtmlToPdf, validateCvSectionOrder, validateLockedSections,
  reorderCvSections, normalizeTextForATS, sectionKey, pageBudgetFor,
} = await core("generate-pdf.mjs");
const { validateCvExperienceOrder } = await core("cv-experience-order.mjs");
const { stripEmptyRenderedSections } = await core("cv-sections-core.mjs");
const { readCvSectionOrder, readLockedSections, readCvPageBudget } = await core("theme-style.mjs");
const { getProfilePath } = await core("path-resolver.mjs");
const { resolvePageFormat } = await core("lib/page-format.mjs");
const { verifyFacts } = await core("verify-cv-facts.mjs");
const envelope = parseCvEnvelope(data.text);
if (!envelope.ok) throw new Error(envelope.error);
const profilePath = getProfilePath(process.cwd());
const source = readFileSync(data.source, "utf8");
let html = stripEmptyRenderedSections(envelope.html);
html = reorderCvSections(html, readCvSectionOrder(profilePath));
validateCvSectionOrder(html, source);
validateCvExperienceOrder(html);
validateLockedSections(html, source, readLockedSections(profilePath, sectionKey));
html = normalizeTextForATS(html).html;
// Check the final printable bytes against the selected variant too. The CLI's
// default fact sources are cv.md; variant B can legitimately contain other owner-verified facts.
const facts = verifyFacts(html, { sourcePaths: [data.source] });
if (facts.verdict === "block") throw new Error("CV fact-check failed after ATS normalization");
const budget = pageBudgetFor("cv", {
  maxPages: 2, maxPagesSupplied: false, strictPages: false,
}, readCvPageBudget(profilePath));
// Upstream rendering logs remain streamed progress; stdout is our JSON channel.
console.log = (...args) => console.error(...args);
const result = await renderHtmlToPdf(html, data.output, {
  format: resolvePageFormat(envelope.format, { profilePath, country: envelope.country }),
  baseDir: path.dirname(data.document), inputPath: data.document,
  workspaceRoot: process.cwd(), kind: "cv", maxPages: budget.maxPages, strictPages: budget.strictPages,
});
process.stdout.write(JSON.stringify(result) + "\n");
