// Copies the latest Prudie mascot into the app. The mascot is developed in the sibling `mascot` folder;
// src/prudie is a read-only copy here, so never edit it here (the next sync would overwrite it).
//   npm run sync:prudie                     uses the default folder below
//   PRUDIE_SRC="D:\path\to\Prudie Mascot" npm run sync:prudie
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";

const source = resolve(process.env.PRUDIE_SRC ?? "../mascot", "src", "prudie");
const target = resolve("src", "prudie");

if (!existsSync(source)) {
  console.error(`Prudie source not found: ${source}\nSet PRUDIE_SRC to the mascot folder.`);
  process.exit(1);
}
rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
cpSync(source, target, { recursive: true });
console.log(`Synced ${readdirSync(target).length} files from ${source} to src/prudie`);
