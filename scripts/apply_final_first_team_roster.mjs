import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

const root = path.resolve(import.meta.dirname, "..");
const sourcePath = path.join(root, "data", "source", "kbo_2025_final_first_team.csv");
const basePath = path.join(root, "data", "players.db");
const savesPath = path.join(root, "data", "kbo_fm_saves.db");
const version = "kbo-2025-regular-season-final-first-team-v2";

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

const roster = parseCsv(fs.readFileSync(sourcePath, "utf8"));
const ids = new Set(roster.map((row) => row.kbo_player_id));
const teamCounts = new Map();
for (const row of roster) teamCounts.set(row.team, (teamCounts.get(row.team) ?? 0) + 1);
if (roster.length !== 326 || ids.size !== 326 || teamCounts.size !== 10) {
  throw new Error(`Invalid final first-team roster: rows=${roster.length} ids=${ids.size} teams=${teamCounts.size}`);
}

const targets = [{ path: basePath, label: "base" }];
const saves = new DatabaseSync(savesPath, { readOnly: true });
for (const save of saves.prepare(
  `SELECT game_saves.id, game_saves.current_date, game_saves.player_db_path
   FROM game_saves
   WHERE game_saves.player_db_path IS NOT NULL
     AND (
       game_saves.current_date <= '2025-11-01'
       OR (
         game_saves.season_day = 1
         AND game_saves.wins = 0
         AND game_saves.losses = 0
         AND game_saves.draws = 0
         AND NOT EXISTS (
           SELECT 1
           FROM simulation_runs
           WHERE simulation_runs.save_id = game_saves.id
         )
         AND NOT EXISTS (
           SELECT 1
           FROM team_roster_decisions
           WHERE team_roster_decisions.save_id = game_saves.id
         )
       )
     )`,
).all()) {
  const databasePath = path.resolve(save.player_db_path);
  if (fs.existsSync(databasePath)) targets.push({ path: databasePath, label: `save-${save.id}` });
}
saves.close();

for (const target of targets) {
  const extension = path.extname(target.path);
  const backupPath = target.path.slice(0, -extension.length) + `.before-final-first-team-v2${extension}`;
  if (!fs.existsSync(backupPath)) fs.copyFileSync(target.path, backupPath);
  const database = new DatabaseSync(target.path);
  try {
    database.exec(`
      CREATE TABLE IF NOT EXISTS first_team_roster_imports (
        version TEXT PRIMARY KEY,
        snapshot_date TEXT NOT NULL,
        player_count INTEGER NOT NULL,
        source_path TEXT NOT NULL,
        imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      );
      BEGIN IMMEDIATE;
      UPDATE players SET status = 0, lineup_pos = 0;
    `);
    const update = database.prepare(
      "UPDATE players SET status = 1 WHERE kbo_player_id = ? AND team = ?",
    );
    let updated = 0;
    for (const row of roster) updated += Number(update.run(row.kbo_player_id, row.team).changes);
    if (updated !== roster.length) throw new Error(`${target.label}: updated=${updated}`);
    database.prepare(`
      INSERT OR REPLACE INTO first_team_roster_imports
        (version, snapshot_date, player_count, source_path, imported_at)
      VALUES (?, '2025-10-31', ?, ?, CURRENT_TIMESTAMP)
    `).run(version, roster.length, sourcePath);
    const ponce = database.prepare(
      "SELECT name, team, status FROM players WHERE kbo_player_id = '55730'",
    ).get();
    if (!ponce || Number(ponce.status) !== 1) throw new Error(`${target.label}: Ponce not registered`);
    database.exec("COMMIT");
    console.log(`APPLIED target=${target.label} players=${updated} ponce_status=${ponce.status}`);
  } catch (error) {
    try { database.exec("ROLLBACK"); } catch {}
    throw error;
  } finally {
    database.close();
  }
}
console.log(`COMPLETE targets=${targets.length} roster=${roster.length}`);
