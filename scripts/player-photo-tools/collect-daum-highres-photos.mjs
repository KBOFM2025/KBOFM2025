import fs from "node:fs";
import path from "node:path";
import process from "node:process";

import sharp from "sharp";

const root = path.resolve(import.meta.dirname, "../..");
const rosterPath = path.resolve(root, process.argv[2] ?? "data/source/kbo_2025_final_roster.csv");
const outputDir = path.resolve(root, process.argv[3] ?? "image/players/local/highres-originals");
const reportPath = path.resolve(root, process.argv[4] ?? "data/source/player_photo_highres_report.json");
const concurrency = Math.max(1, Math.min(12, Number(process.env.PLAYER_PHOTO_DOWNLOADS ?? 8)));

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < text.length; index++) {
    const character = text[index];
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') {
        field += '"';
        index++;
      } else if (character === '"') {
        quoted = false;
      } else {
        field += character;
      }
    } else if (character === '"') {
      quoted = true;
    } else if (character === ",") {
      row.push(field);
      field = "";
    } else if (character === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += character;
    }
  }
  if (field.length || row.length) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }
  const headers = rows.shift();
  return rows.filter((values) => values.some(Boolean)).map((values) =>
    Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])),
  );
}

const roster = parseCsv(fs.readFileSync(rosterPath, "utf8"));
if (roster.length !== 636) throw new Error(`Expected 636 roster rows, got ${roster.length}`);
fs.mkdirSync(outputDir, { recursive: true });

const report = new Array(roster.length);
let nextIndex = 0;
let downloaded = 0;
let skipped = 0;
let failed = 0;

async function downloadPlayer(player, index) {
  const id = String(player.kbo_player_id);
  const url = `https://t1.daumcdn.net/sports/player/300/1/${id}.jpg`;
  const target = path.join(outputDir, `${id}.jpg`);
  try {
    if (fs.existsSync(target)) {
      const metadata = await sharp(target).metadata();
      if (Math.max(metadata.width, metadata.height) >= 500) {
        skipped++;
        report[index] = {
          kbo_player_id: id,
          name: player.name,
          team: player.team,
          status: "already_downloaded",
          source_url: url,
          width: metadata.width,
          height: metadata.height,
          local_filename: path.relative(root, target).replaceAll("\\", "/"),
        };
        return;
      }
    }

    const response = await fetch(url, { headers: { "User-Agent": "KBOFM2025-LocalPhotoCollector/2.0" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const buffer = Buffer.from(await response.arrayBuffer());
    if (buffer.length < 20_000) throw new Error(`Unexpectedly small image (${buffer.length} bytes)`);
    const metadata = await sharp(buffer).metadata();
    if (Math.max(metadata.width, metadata.height) < 500) {
      throw new Error(`Image is not high resolution (${metadata.width}x${metadata.height})`);
    }
    fs.writeFileSync(target, buffer);
    downloaded++;
    report[index] = {
      kbo_player_id: id,
      name: player.name,
      team: player.team,
      status: "downloaded",
      source_url: url,
      width: metadata.width,
      height: metadata.height,
      source_quality: Math.min(metadata.width, metadata.height) >= 800 ? "high" : "medium",
      bytes: buffer.length,
      local_filename: path.relative(root, target).replaceAll("\\", "/"),
    };
  } catch (error) {
    failed++;
    report[index] = {
      kbo_player_id: id,
      name: player.name,
      team: player.team,
      status: "failed",
      source_url: url,
      error: error.message,
    };
    process.stderr.write(`FAILED ${id} ${player.name}: ${error.message}\n`);
  }
}

async function worker() {
  while (true) {
    const index = nextIndex++;
    if (index >= roster.length) return;
    await downloadPlayer(roster[index], index);
    const processed = downloaded + skipped + failed;
    if (processed % 25 === 0 || processed === roster.length) {
      process.stdout.write(
        `PROGRESS ${processed}/${roster.length} downloaded=${downloaded} skipped=${skipped} failed=${failed}\n`,
      );
    }
  }
}

await Promise.all(Array.from({ length: concurrency }, () => worker()));
fs.writeFileSync(
  reportPath,
  `${JSON.stringify(
    {
      generated_at: new Date().toISOString(),
      source: "Daum Sports KBO player original image endpoint",
      rights_note: "Redistribution rights unverified; downloaded files are local-only and Git-ignored.",
      totals: { roster: roster.length, downloaded, skipped, failed },
      players: report,
    },
    null,
    2,
  )}\n`,
);
process.stdout.write(
  `COMPLETE total=${roster.length} downloaded=${downloaded} skipped=${skipped} failed=${failed}\n`,
);
if (failed > 1) process.exitCode = 1;
