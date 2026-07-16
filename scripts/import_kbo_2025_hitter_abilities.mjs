import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDirectory, "..");
const csvPath = path.join(projectRoot, "data", "source", "kbo_2025_hitter_abilities.csv");
const databasePath = path.join(projectRoot, "data", "players.db");
const backupPath = path.join(projectRoot, "data", "players.before-hitter-abilities-v2.db");

const ratingColumns = [
  "contact", "power", "plate_discipline", "bat_control",
  "timing", "bunt", "speed", "baserunning_judgment",
];
const futureColumns = [
  "fielding_range", "catching", "throwing_power", "throwing_accuracy",
  "fielding_judgment", "composure", "leadership", "aggressiveness",
];
const extraColumns = {
  ...Object.fromEntries([...ratingColumns, ...futureColumns].map((column) => [column, "INTEGER"])),
  ability_source_level: "TEXT",
  ability_formula_version: "TEXT",
};

function parseCsv(text) {
  const records = [];
  let record = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (character === '"') {
        quoted = false;
      } else {
        field += character;
      }
    } else if (character === '"') {
      quoted = true;
    } else if (character === ",") {
      record.push(field);
      field = "";
    } else if (character === "\n") {
      record.push(field.replace(/\r$/, ""));
      if (record.some((value) => value !== "")) records.push(record);
      record = [];
      field = "";
    } else {
      field += character;
    }
  }
  if (field !== "" || record.length) {
    record.push(field.replace(/\r$/, ""));
    records.push(record);
  }
  const headers = records.shift().map((header) => header.replace(/^\uFEFF/, ""));
  return records.map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])));
}

if (!fs.existsSync(csvPath)) throw new Error(`Ability CSV not found: ${csvPath}`);
if (!fs.existsSync(databasePath)) throw new Error(`Player database not found: ${databasePath}`);
if (!fs.existsSync(backupPath)) fs.copyFileSync(databasePath, backupPath);

const rows = parseCsv(fs.readFileSync(csvPath, "utf8"));
if (rows.length !== 317) throw new Error(`Expected 317 ability rows, got ${rows.length}`);
const ids = new Set(rows.map((row) => row.kbo_player_id));
if (ids.size !== rows.length || ids.has("")) throw new Error("KBO player IDs must be present and unique");
const versions = new Set(rows.map((row) => row.formula_version));
if (versions.size !== 1 || versions.has("")) throw new Error("Expected one non-empty formula version");
for (const row of rows) {
  for (const column of ratingColumns) {
    const rating = Number(row[column]);
    if (!Number.isInteger(rating) || rating < 1 || rating > 20) {
      throw new Error(`Rating out of range: ${row.kbo_player_id} ${column}=${row[column]}`);
    }
  }
  for (const column of futureColumns) {
    if ((row[column] ?? "").trim() !== "") {
      throw new Error(`Future ability must be blank: ${row.kbo_player_id} ${column}`);
    }
  }
}

const formulaVersion = [...versions][0];
const database = new DatabaseSync(databasePath);
try {
  const existingColumns = new Set(database.prepare("PRAGMA table_info(players)").all().map((row) => row.name));
  for (const [column, declaration] of Object.entries(extraColumns)) {
    if (!existingColumns.has(column)) database.exec(`ALTER TABLE players ADD COLUMN ${column} ${declaration}`);
  }
  database.exec(`
    CREATE TABLE IF NOT EXISTS hitter_ability_imports (
      formula_version TEXT PRIMARY KEY,
      player_count INTEGER NOT NULL,
      source_path TEXT NOT NULL,
      imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
  `);
  database.exec(`
    DROP VIEW IF EXISTS player_defense_abilities;
    CREATE VIEW player_defense_abilities AS
    SELECT id AS player_id, player_uid, kbo_player_id, team, name,
           fielding_range, catching, throwing_power,
           throwing_accuracy, fielding_judgment
    FROM players;

    DROP VIEW IF EXISTS player_mental_abilities;
    CREATE VIEW player_mental_abilities AS
    SELECT id AS player_id, player_uid, kbo_player_id, team, name,
           composure, leadership, aggressiveness
    FROM players;
  `);

  const rosterIds = new Set(database.prepare("SELECT kbo_player_id FROM players WHERE position_group <> 'P'").all().map((row) => row.kbo_player_id));
  const missing = [...rosterIds].filter((id) => !ids.has(id));
  const unknown = [...ids].filter((id) => !rosterIds.has(id));
  if (missing.length || unknown.length) {
    throw new Error(`Ability IDs do not match hitter roster (missing=${missing.length}, unknown=${unknown.length})`);
  }

  const ratingAssignments = ratingColumns.map((column) => `${column} = ?`).join(", ");
  const futureAssignments = futureColumns.map((column) => `${column} = NULL`).join(", ");
  const update = database.prepare(`
    UPDATE players SET ${ratingAssignments}, ${futureAssignments},
      ability_source_level = ?, ability_formula_version = ?
    WHERE kbo_player_id = ? AND position_group <> 'P'
  `);
  const saveHistory = database.prepare(`
    INSERT OR REPLACE INTO hitter_ability_imports
      (formula_version, player_count, source_path, imported_at)
    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
  `);

  database.exec("BEGIN IMMEDIATE");
  let updated = 0;
  try {
    for (const row of rows) {
      const values = ratingColumns.map((column) => Number(row[column]));
      values.push(row.source_level ?? "", formulaVersion, row.kbo_player_id);
      updated += Number(update.run(...values).changes);
    }
    if (updated !== rows.length) throw new Error(`Expected 317 updates, got ${updated}`);
    saveHistory.run(formulaVersion, rows.length, csvPath);
    database.exec("COMMIT");
  } catch (error) {
    database.exec("ROLLBACK");
    throw error;
  }

  const imported = database.prepare("SELECT COUNT(*) AS count FROM players WHERE position_group <> 'P' AND ability_formula_version = ?").get(formulaVersion).count;
  const pitcherValues = database.prepare(`SELECT COUNT(*) AS count FROM players WHERE position_group = 'P' AND (${ratingColumns.map((column) => `${column} IS NOT NULL`).join(" OR ")})`).get().count;
  const populatedFutureValues = database.prepare(`SELECT COUNT(*) AS count FROM players WHERE ${futureColumns.map((column) => `${column} IS NOT NULL`).join(" OR ")}`).get().count;
  const defenseViewColumns = database.prepare("PRAGMA table_info(player_defense_abilities)").all().map((row) => row.name);
  const mentalViewColumns = database.prepare("PRAGMA table_info(player_mental_abilities)").all().map((row) => row.name);
  database.prepare("ATTACH DATABASE ? AS before_db").run(backupPath);
  const changedLegacyValues = database.prepare(`
    SELECT COUNT(*) AS count
    FROM players current
    JOIN before_db.players previous ON previous.kbo_player_id = current.kbo_player_id
    WHERE current.con <> previous.con OR current.pow <> previous.pow
       OR current.eye <> previous.eye OR current.def <> previous.def
  `).get().count;
  database.exec("DETACH DATABASE before_db");
  if (Number(imported) !== 317 || Number(pitcherValues) !== 0 || Number(populatedFutureValues) !== 0 || Number(changedLegacyValues) !== 0) {
    throw new Error(`Verification failed: hitters=${imported}, pitcher_values=${pitcherValues}, future_values=${populatedFutureValues}, changed_legacy=${changedLegacyValues}`);
  }
  if (!futureColumns.slice(0, 5).every((column) => defenseViewColumns.includes(column)) ||
      !futureColumns.slice(5).every((column) => mentalViewColumns.includes(column))) {
    throw new Error("Defense and mental ability views are incomplete");
  }
  const sampleRow = rows.find((row) => row.player_name === "김도영");
  const sample = database.prepare(`
    SELECT name, contact, power, plate_discipline, bat_control, timing, bunt,
           speed, baserunning_judgment, fielding_range, catching,
           throwing_power, throwing_accuracy, fielding_judgment,
           composure, leadership, aggressiveness
    FROM players WHERE kbo_player_id = ?
  `).get(sampleRow.kbo_player_id);
  console.log(`COMPLETE hitters=${imported} pitchers_with_new_values=${pitcherValues} future_values=${populatedFutureValues} changed_legacy=${changedLegacyValues} formula=${formulaVersion}`);
  console.log(`SAMPLE ${JSON.stringify(sample)}`);
  console.log(`BACKUP ${backupPath}`);
} finally {
  database.close();
}
