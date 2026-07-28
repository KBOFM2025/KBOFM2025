import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

const root=path.resolve(import.meta.dirname,"..");
const basePath=path.join(root,"data","players.db");
const savesPath=path.join(root,"data","kbo_fm_saves.db");
const ratings=["pitcher_velocity","pitcher_stuff","pitcher_command","pitcher_movement","pitcher_stamina","pitcher_pitchability","pitcher_strikeout","pitcher_walk_control","pitcher_composure","pitch_four_seam","pitch_sinker","pitch_cutter","pitch_changeup","pitch_slider","pitch_curve","pitch_splitter","pitch_sweeper","pitch_knuckleball"];
const base=new DatabaseSync(basePath,{readOnly:true});
const baseRows=base.prepare(`SELECT id,kbo_player_id,team,age,${ratings.join(",")},pitcher_repertoire,pitcher_pitch_detail_json,pitcher_source_level,pitcher_formula_version FROM players WHERE position_group='P'`).all();
if(baseRows.length!==319)throw new Error(`Base pitchers=${baseRows.length}`);
for(const row of baseRows){for(const column of ratings){if(row[column]!==null&&(row[column]<1||row[column]>20))throw new Error(`Out of range ${row.kbo_player_id} ${column}`);}}
const populated=baseRows.filter((row)=>row.pitcher_formula_version).length;
const tracked=baseRows.filter((row)=>row.pitcher_repertoire).length;
const fourSeam=baseRows.filter((row)=>row.pitch_four_seam!==null).length;
const slider=baseRows.filter((row)=>row.pitch_slider!==null).length;
if(fourSeam===0||slider===0)throw new Error(`Pitch ratings missing: four_seam=${fourSeam} slider=${slider}`);
const detailed=baseRows.filter((row)=>{try{return JSON.parse(row.pitcher_pitch_detail_json??"[]").length>0;}catch{return false;}}).length;
if(detailed!==tracked)throw new Error(`Pitch detail mismatch: tracked=${tracked} detailed=${detailed}`);
const byId=new Map(baseRows.map((row)=>[String(row.kbo_player_id),row]));
base.close();
const saves=new DatabaseSync(savesPath,{readOnly:true});const saveRows=saves.prepare("SELECT id,base_team,player_db_path FROM game_saves WHERE player_db_path IS NOT NULL").all();saves.close();
let checked=0;
for(const save of saveRows){if(!fs.existsSync(save.player_db_path))continue;const db=new DatabaseSync(save.player_db_path,{readOnly:true});const rows=db.prepare(`SELECT id,kbo_player_id,team,age,${ratings.join(",")} FROM players WHERE position_group='P'`).all();db.close();if(rows.length!==319)throw new Error(`Save ${save.id} pitchers=${rows.length}`);for(const row of rows){const original=byId.get(String(row.kbo_player_id));for(const column of ratings){if(original[column]===null){if(row[column]!==null)throw new Error(`Null changed ${save.id} ${row.kbo_player_id} ${column}`);continue;}const difference=Number(row[column])-Number(original[column]);if(row.team===save.base_team||Number(row.age)>=30){if(difference!==0)throw new Error(`Fixed player changed ${save.id} ${row.kbo_player_id} ${column} ${difference}`);}else if(Math.abs(difference)>2){throw new Error(`U30 delta too large ${save.id} ${row.kbo_player_id} ${column} ${difference}`);}}}checked+=1;}
console.log(`COMPLETE base_pitchers=${baseRows.length} populated=${populated} tracked=${tracked} detailed=${detailed} four_seam=${fourSeam} slider=${slider} save_databases=${checked}`);
