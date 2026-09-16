import fs from "node:fs";
import path from "node:path";
import process from "node:process";

import sharp from "sharp";

const rosterText = fs.readFileSync("data/source/kbo_2025_final_roster.csv", "utf8");
const rosterIds = rosterText
  .trim()
  .split(/\r?\n/)
  .slice(1)
  .map((line) => line.split(",")[1].replaceAll('"', ""));
const directory = "image/players/local/game-ready";
const files = fs
  .readdirSync(directory)
  .filter((name) => /^\d+\.(?:jpe?g|png)$/i.test(name));
const fileIds = new Set(files.map((name) => path.parse(name).name));
const invalid = [];

for (const filename of files) {
  try {
    const metadata = await sharp(path.join(directory, filename)).metadata();
    if (!metadata.width || !metadata.height || metadata.width > 1600 || metadata.height > 1600) {
      invalid.push({ filename, width: metadata.width, height: metadata.height });
    }
  } catch (error) {
    invalid.push({ filename, error: error.message });
  }
}

const result = {
  generatedAt: new Date().toISOString(),
  pipeline: "high-resolution source, original background, aspect ratio preserved",
  roster: rosterIds.length,
  files: files.length,
  uniqueIds: fileIds.size,
  missing: rosterIds.filter((id) => !fileIds.has(id)),
  invalid,
};
const reportPath = path.resolve(
  process.argv[2] ?? "data/source/player_photo_connection_report.json",
);
fs.writeFileSync(reportPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");
process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
