import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDirectory, "..");
const outputPath = path.join(
  projectRoot,
  "data",
  "source",
  "kbo_2025_advanced_hitter_metrics.csv",
);

const teams = [
  ["두산 베어스", "doosanbears"],
  ["한화 이글스", "hanwhaeagles"],
  ["KIA 타이거즈", "kiatigers"],
  ["키움 히어로즈", "kiwoomheroes"],
  ["KT 위즈", "ktwiz"],
  ["LG 트윈스", "lgtwins"],
  ["롯데 자이언츠", "lottegiants"],
  ["NC 다이노스", "ncdinos"],
  ["삼성 라이온즈", "samsunglions"],
  ["SSG 랜더스", "ssglanders"],
];

function plainText(value) {
  return value
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, " ")
    .trim();
}

function csvCell(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function parseTeamPage(html, team, sourceUrl) {
  const firstTableStart = html.indexOf('<table class="table table-striped table-hover"');
  if (firstTableStart < 0) throw new Error(`Batting table not found: ${sourceUrl}`);
  const firstTableEnd = html.indexOf("</table>", firstTableStart);
  const table = html.slice(firstTableStart, firstTableEnd);
  const bodyMatch = table.match(/<tbody>([\s\S]*?)<\/tbody>/i);
  if (!bodyMatch) throw new Error(`Batting table body not found: ${sourceUrl}`);

  const rows = [];
  for (const rowMatch of bodyMatch[1].matchAll(/<tr>([\s\S]*?)<\/tr>/gi)) {
    const cells = [...rowMatch[1].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/gi)].map(
      (match) => plainText(match[1]),
    );
    if (cells.length !== 11) continue;
    const playerHref = rowMatch[1].match(/href="\/players\/(\d+)"/i)?.[1] ?? "";
    const nameParts = cells[0].split("|").map((part) => part.trim());
    const playerName = nameParts.length > 1 ? nameParts.at(-1) : nameParts[0];
    rows.push({
      season: 2025,
      source_team: team,
      player_name: playerName,
      public_player_id: playerHref,
      position: cells[1],
      age: cells[2],
      PA: cells[3],
      BB_pct: cells[4],
      SO_pct: cells[5],
      ISO: cells[6],
      BABIP: cells[7],
      wRC_plus: cells[8],
      SFR: cells[9],
      WAR: cells[10],
      source_url: sourceUrl,
    });
  }
  return rows;
}

const output = [];
for (const [team, slug] of teams) {
  const sourceUrl = `https://www.kbofancystats.com/teams/${slug}/`;
  const response = await fetch(sourceUrl, {
    headers: { "User-Agent": "KBO-FM-data-audit/1.0" },
  });
  if (!response.ok) throw new Error(`${sourceUrl}: HTTP ${response.status}`);
  const rows = parseTeamPage(await response.text(), team, sourceUrl);
  if (!rows.length) throw new Error(`No hitter rows found: ${sourceUrl}`);
  output.push(...rows);
  console.log(`FETCHED team=${team} hitters=${rows.length}`);
}

const columns = [
  "season",
  "source_team",
  "player_name",
  "public_player_id",
  "position",
  "age",
  "PA",
  "BB_pct",
  "SO_pct",
  "ISO",
  "BABIP",
  "wRC_plus",
  "SFR",
  "WAR",
  "source_url",
];
const csv = [
  columns.map(csvCell).join(","),
  ...output.map((row) => columns.map((column) => csvCell(row[column])).join(",")),
].join("\n") + "\n";

fs.writeFileSync(outputPath, csv, "utf8");
console.log(`COMPLETE hitters=${output.length} output=${outputPath}`);
