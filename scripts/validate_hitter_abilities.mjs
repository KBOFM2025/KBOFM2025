import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

const root = path.resolve(import.meta.dirname, "..");
const sourcePath = path.join(root, "data", "source", "kbo_2025_hitter_abilities.csv");
const playersPath = path.join(root, "data", "players.db");
const savesPath = path.join(root, "data", "kbo_fm_saves.db");
const expectedFormula = "kbo-hitter-abilities-v7-cross-role-calibrated";
const ratings = [
  "contact", "power", "plate_discipline", "bat_control", "timing", "bunt",
  "speed", "baserunning_judgment", "fielding_range", "catching",
  "throwing_power", "throwing_accuracy", "fielding_judgment",
  "composure", "leadership", "aggressiveness",
];
const metadata = [
  "hitter_advanced_public_player_id", "hitter_advanced_wrc_plus",
  "hitter_advanced_sfr", "hitter_advanced_war", "hitter_advanced_source_url",
  "hitter_rating_confidence", "hitter_rating_detail_json",
];

function parseCsv(text) {
  const records = []; let record = [], field = "", quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') { field += '"'; index += 1; }
      else if (character === '"') quoted = false;
      else field += character;
    } else if (character === '"') quoted = true;
    else if (character === ",") { record.push(field); field = ""; }
    else if (character === "\n") {
      record.push(field.replace(/\r$/, ""));
      if (record.some(Boolean)) records.push(record);
      record = []; field = "";
    } else field += character;
  }
  const headers = records.shift().map((value) => value.replace(/^\uFEFF/, ""));
  return records.map((values) =>
    Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])));
}

function average(rows, columns) {
  const values = rows.map((row) =>
    columns.reduce((sum, column) => sum + Number(row[column]), 0) / columns.length);
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

const sourceRows = parseCsv(fs.readFileSync(sourcePath, "utf8"));
if (sourceRows.length !== 317) throw new Error(`Expected 317 hitters, got ${sourceRows.length}`);
const ids = new Set(sourceRows.map((row) => row.kbo_player_id));
if (ids.size !== 317 || ids.has("")) throw new Error("Hitter IDs are empty or duplicated");
for (const row of sourceRows) {
  if (row.formula_version !== expectedFormula) throw new Error(`Wrong formula: ${row.kbo_player_id}`);
  for (const column of ratings) {
    const value = Number(row[column]);
    if (!Number.isInteger(value) || value < 1 || value > 20) {
      throw new Error(`Invalid rating: ${row.kbo_player_id} ${column}=${row[column]}`);
    }
  }
  JSON.parse(row.rating_detail_json);
}

const kboRows = sourceRows.filter((row) => row.source_level === "KBO");
const futuresRows = sourceRows.filter((row) => row.source_level === "FUTURES");
const offense = ratings.slice(0, 5).concat(ratings.slice(6, 8));
const kboMean = average(kboRows, offense);
const futuresMean = average(futuresRows, offense);
if (kboMean - futuresMean < 1.5) throw new Error("KBO/Futures rating separation is too small");
const advancedCount = sourceRows.filter((row) => row.advanced_public_player_id).length;
if (advancedCount < 200) throw new Error(`Advanced metric coverage too low: ${advancedCount}`);

const base = new DatabaseSync(playersPath, { readOnly: true });
const baseColumns = new Set(base.prepare("PRAGMA table_info(players)").all().map((row) => row.name));
for (const column of metadata) if (!baseColumns.has(column)) throw new Error(`Missing DB column: ${column}`);
const baseRows = base.prepare("SELECT * FROM players WHERE position_group <> 'P'").all();
if (baseRows.length !== 317) throw new Error(`Base DB hitter count=${baseRows.length}`);
const baseById = new Map(baseRows.map((row) => [String(row.kbo_player_id), row]));
for (const source of sourceRows) {
  const row = baseById.get(source.kbo_player_id);
  if (!row) throw new Error(`Base DB missing hitter ${source.kbo_player_id}`);
  if (row.ability_formula_version !== expectedFormula) throw new Error(`Base formula mismatch ${source.kbo_player_id}`);
  for (const column of ratings) {
    if (Number(row[column]) !== Number(source[column])) {
      throw new Error(`Base rating mismatch ${source.kbo_player_id} ${column}`);
    }
  }
}
base.close();

const saves = new DatabaseSync(savesPath, { readOnly: true });
const saveRows = saves.prepare(
  "SELECT id, base_team, player_db_path FROM game_saves WHERE player_db_path IS NOT NULL",
).all();
saves.close();
let checkedSaves = 0;
for (const save of saveRows) {
  const databasePath = path.resolve(save.player_db_path);
  if (!fs.existsSync(databasePath)) continue;
  const database = new DatabaseSync(databasePath, { readOnly: true });
  const players = database.prepare("SELECT * FROM players WHERE position_group <> 'P'").all();
  for (const player of players) {
    const original = baseById.get(String(player.kbo_player_id));
    for (const column of ratings) {
      const difference = Number(player[column]) - Number(original[column]);
      const fixed = player.team === save.base_team || Number(player.age) >= 30;
      if (fixed && difference !== 0) {
        throw new Error(`Save ${save.id} fixed-player drift ${player.name} ${column}=${difference}`);
      }
      if (!fixed && Math.abs(difference) > 2) {
        throw new Error(`Save ${save.id} U30 drift ${player.name} ${column}=${difference}`);
      }
    }
    if (player.hitter_rating_detail_json !== original.hitter_rating_detail_json) {
      throw new Error(`Save ${save.id} evidence mismatch ${player.name}`);
    }
  }
  database.close();
  checkedSaves += 1;
}

console.log(
  `COMPLETE hitters=317 KBO=${kboRows.length} FUTURES=${futuresRows.length}` +
  ` advanced=${advancedCount} KBO_mean=${kboMean.toFixed(2)}` +
  ` FUTURES_mean=${futuresMean.toFixed(2)} saves=${checkedSaves}`,
);
