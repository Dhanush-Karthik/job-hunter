import { pathToFileURL } from "node:url";
import path from "node:path";

process.on("uncaughtException", (error) => {
  console.error(error.message);
  process.exit(1);
});

export const vendor = path.resolve(process.argv[2]);
export const core = (name) => import(pathToFileURL(path.join(vendor, name)).href);
export async function input() {
  let text = "";
  for await (const chunk of process.stdin) text += chunk;
  return JSON.parse(text);
}
export const output = (value) => console.log(JSON.stringify(value));
