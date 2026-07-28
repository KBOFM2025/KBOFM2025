import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

const root = path.resolve(import.meta.dirname, "..");
const csvPath = path.join(root, "data", "source", "kbo_2025_pitcher_abilities.csv");
const databasePath = path.join(root, "data", "players.db");
const backupPath = path.join(root, "data", "players.before-pitcher-abilities-v1.db");
const ratingColumns = [
  "pitcher_velocity", "pitcher_stuff", "pitcher_command", "pitcher_movement",
  "pitcher_stamina", "pitcher_pitchability", "pitcher_strikeout",
  "pitcher_walk_control", "pitcher_composure", "pitch_four_seam", "pitch_sinker",
  "pitch_cutter", "pitch_changeup", "pitch_slider", "pitch_curve", "pitch_splitter",
  "pitch_sweeper", "pitch_knuckleball",
];
const metadataColumns = {
  pitcher_repertoire: "TEXT", pitcher_source_level: "TEXT", pitcher_confidence: "TEXT",
  pitcher_formula_version: "TEXT", pitcher_sample_tbf: "INTEGER", pitcher_sample_ip: "REAL",
  pitcher_avg_velocity: "REAL", pitcher_k_stuff_plus: "REAL", pitcher_k_location_plus: "REAL",
  pitcher_whiff_rate: "REAL", pitcher_csw_rate: "REAL", pitcher_k_rate: "REAL",
  pitcher_bb_rate: "REAL", pitcher_hr_rate: "REAL", pitcher_fip: "REAL",
  pitcher_pitch_detail_json: "TEXT",
  pitcher_tracking_source_url: "TEXT",
};

function parseCsv(text) {
  const records=[]; let record=[],field="",quoted=false;
  for(let i=0;i<text.length;i+=1){const c=text[i];if(quoted){if(c==='"'&&text[i+1]==='"'){field+='"';i+=1;}else if(c==='"')quoted=false;else field+=c;}else if(c==='"')quoted=true;else if(c===","){record.push(field);field="";}else if(c==="\n"){record.push(field.replace(/\r$/, ""));if(record.some(Boolean))records.push(record);record=[];field="";}else field+=c;}
  if(field||record.length){record.push(field.replace(/\r$/, ""));records.push(record);}
  const headers=records.shift().map((v)=>v.replace(/^\uFEFF/,""));
  return records.map((values)=>Object.fromEntries(headers.map((header,index)=>[header,values[index]??""])));
}
const nullableNumber=(value)=>String(value??"").trim()===""?null:Number(value);
const rows=parseCsv(fs.readFileSync(csvPath,"utf8"));
if(rows.length!==319)throw new Error(`Expected 319 pitchers, got ${rows.length}`);
const ids=new Set(rows.map((row)=>row.kbo_player_id));if(ids.size!==319||ids.has(""))throw new Error("Pitcher IDs must be unique");
for(const row of rows){for(const column of ratingColumns){if(row[column]==="")continue;const value=Number(row[column]);if(!Number.isInteger(value)||value<1||value>20)throw new Error(`Invalid rating ${row.kbo_player_id} ${column}=${row[column]}`);}}
const formulaVersion=rows[0].formula_version;if(!formulaVersion||rows.some((row)=>row.formula_version!==formulaVersion))throw new Error("Formula versions differ");
if(!fs.existsSync(backupPath))fs.copyFileSync(databasePath,backupPath);
const db=new DatabaseSync(databasePath);
try{
  const existing=new Set(db.prepare("PRAGMA table_info(players)").all().map((row)=>row.name));
  for(const column of ratingColumns){if(!existing.has(column))db.exec(`ALTER TABLE players ADD COLUMN ${column} INTEGER`);}
  for(const [column,type] of Object.entries(metadataColumns)){if(!existing.has(column))db.exec(`ALTER TABLE players ADD COLUMN ${column} ${type}`);}
  db.exec(`CREATE TABLE IF NOT EXISTS pitcher_ability_imports(formula_version TEXT PRIMARY KEY,player_count INTEGER NOT NULL,source_path TEXT NOT NULL,imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`);
  const rosterIds=new Set(db.prepare("SELECT kbo_player_id FROM players WHERE position_group='P'").all().map((row)=>String(row.kbo_player_id)));
  if(rosterIds.size!==319||[...ids].some((id)=>!rosterIds.has(id)))throw new Error("Pitcher CSV does not match player database");
  const allColumns=[...ratingColumns,...Object.keys(metadataColumns)];
  const update=db.prepare(`UPDATE players SET ${allColumns.map((column)=>`${column}=?`).join(",")},salary=COALESCE(?,salary),ability_source_level=?,ability_formula_version=? WHERE kbo_player_id=? AND position_group='P'`);
  db.exec("BEGIN IMMEDIATE");let updated=0;
  try{for(const row of rows){const values=ratingColumns.map((column)=>nullableNumber(row[column]));values.push(row.repertoire,row.source_level,row.confidence,row.formula_version,nullableNumber(row.sample_tbf),nullableNumber(row.sample_ip),nullableNumber(row.avg_velocity),nullableNumber(row.k_stuff_plus),nullableNumber(row.k_location_plus),nullableNumber(row.whiff_rate),nullableNumber(row.csw_rate),nullableNumber(row.k_rate),nullableNumber(row.bb_rate),nullableNumber(row.hr_rate),nullableNumber(row.fip),row.pitch_detail_json,row.tracking_source_url);values.push(nullableNumber(row.salary_10k_krw),row.source_level,row.formula_version,row.kbo_player_id);updated+=Number(update.run(...values).changes);}if(updated!==319)throw new Error(`Updated ${updated}/319`);db.prepare("INSERT OR REPLACE INTO pitcher_ability_imports(formula_version,player_count,source_path,imported_at) VALUES(?,?,?,CURRENT_TIMESTAMP)").run(formulaVersion,319,csvPath);db.exec("COMMIT");}catch(error){db.exec("ROLLBACK");throw error;}
  const verified=db.prepare("SELECT COUNT(*) count FROM players WHERE position_group='P' AND pitcher_formula_version=?").get(formulaVersion).count;
  console.log(`COMPLETE pitchers=${verified} formula=${formulaVersion} backup=${backupPath}`);
}finally{db.close();}
