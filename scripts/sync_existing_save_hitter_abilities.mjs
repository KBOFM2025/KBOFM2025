import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

const root = path.resolve(import.meta.dirname, "..");
const sourcePath = path.join(root, "data", "source", "kbo_2025_hitter_abilities.csv");
const savesPath = path.join(root, "data", "kbo_fm_saves.db");
const ratingColumns = [
  "contact", "power", "plate_discipline", "bat_control",
  "timing", "bunt", "speed", "baserunning_judgment",
  "fielding_range", "catching", "throwing_power", "throwing_accuracy",
  "fielding_judgment", "composure", "leadership", "aggressiveness",
];
const metadataColumns = [
  "hitter_advanced_public_player_id", "hitter_advanced_wrc_plus",
  "hitter_advanced_sfr", "hitter_advanced_war", "hitter_advanced_source_url",
  "hitter_rating_confidence", "hitter_rating_detail_json",
];
const metadataSourceColumns = [
  "advanced_public_player_id", "advanced_wrc_plus", "advanced_sfr",
  "advanced_war", "advanced_source_url", "rating_confidence", "rating_detail_json",
];
const metadataDeclarations = {
  hitter_advanced_public_player_id: "TEXT",
  hitter_advanced_wrc_plus: "REAL",
  hitter_advanced_sfr: "REAL",
  hitter_advanced_war: "REAL",
  hitter_advanced_source_url: "TEXT",
  hitter_rating_confidence: "TEXT",
  hitter_rating_detail_json: "TEXT",
};

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
    else if (character === "\n") { record.push(field.replace(/\r$/, "")); if (record.some(Boolean)) records.push(record); record = []; field = ""; }
    else field += character;
  }
  if (field || record.length) { record.push(field.replace(/\r$/, "")); records.push(record); }
  const headers = records.shift().map((value) => value.replace(/^\uFEFF/, ""));
  return records.map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])));
}

function delta(saveId, playerId, column) {
  return crypto.createHash("sha256").update(`${saveId}:${playerId}:${column}`).digest()[0] % 5 - 2;
}

const abilities = parseCsv(fs.readFileSync(sourcePath, "utf8"));
if (abilities.length !== 317) throw new Error(`Expected 317 hitters, got ${abilities.length}`);
const saves = new DatabaseSync(savesPath, { readOnly: true });
const records = saves.prepare("SELECT id, base_team, player_db_path FROM game_saves WHERE player_db_path IS NOT NULL").all();
saves.close();

let databases = 0; let players = 0;
for (const save of records) {
  const databasePath = path.resolve(save.player_db_path);
  if (!fs.existsSync(databasePath)) continue;
  const backupPath = databasePath.replace(/\.sqlite$/i, ".before-hitter-v7.sqlite");
  if (!fs.existsSync(backupPath)) fs.copyFileSync(databasePath, backupPath);
  const database = new DatabaseSync(databasePath);
  try {
    const existingColumns = new Set(database.prepare("PRAGMA table_info(players)").all().map((row) => row.name));
    for (const [column, declaration] of Object.entries(metadataDeclarations)) {
      if (!existingColumns.has(column)) database.exec(`ALTER TABLE players ADD COLUMN ${column} ${declaration}`);
    }
    const playersById = new Map(database.prepare("SELECT id,kbo_player_id,team,age FROM players WHERE position_group <> 'P'").all().map((row) => [String(row.kbo_player_id), row]));
    const assignments = [...ratingColumns, ...metadataColumns].map((column) => `${column}=?`).join(",");
    const update = database.prepare(`UPDATE players SET ${assignments}, salary=COALESCE(?,salary), ability_formula_version=? WHERE id=?`);
    database.exec("BEGIN IMMEDIATE");
    let updated = 0;
    try {
      for (const ability of abilities) {
        const player = playersById.get(String(ability.kbo_player_id));
        if (!player) continue;
        const values = ratingColumns.map((column) => {
          let value = Number(ability[column]);
          if (player.team !== save.base_team && Number(player.age) < 30) value += delta(save.id, player.id, column);
          return Math.max(1, Math.min(20, value));
        });
        values.push(...metadataSourceColumns.map((column) => {
          const value = ability[column];
          if (value === "") return null;
          return ["advanced_wrc_plus", "advanced_sfr", "advanced_war"].includes(column)
            ? Number(value)
            : value;
        }));
        const verifiedSalary = (ability.salary_10k_krw ?? "").trim();
        values.push(verifiedSalary === "" ? null : Number(verifiedSalary));
        values.push(ability.formula_version, player.id);
        updated += Number(update.run(...values).changes);
      }
      if (updated !== 317) throw new Error(`Save ${save.id}: expected 317 updates, got ${updated}`);
      database.exec("COMMIT");
    } catch (error) { database.exec("ROLLBACK"); throw error; }
    databases += 1; players += updated;
  } finally { database.close(); }
}
console.log(`COMPLETE databases=${databases} hitters=${players}`);
