import path from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const databasePath = path.resolve(scriptDirectory, "..", "data", "kbo_fm_saves.db");
const database = new DatabaseSync(databasePath);

try {
  database.exec(`
    CREATE TABLE IF NOT EXISTS daily_news (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      save_id INTEGER NOT NULL,
      news_date TEXT NOT NULL,
      category TEXT NOT NULL,
      headline TEXT NOT NULL,
      body TEXT NOT NULL,
      is_read INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      UNIQUE(save_id, news_date, headline)
    )
  `);
  const table = database.prepare(
    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'daily_news'"
  ).get();
  const saves = database.prepare("SELECT COUNT(*) AS count FROM game_saves").get();
  if (!table) throw new Error("daily_news migration failed");
  console.log(`COMPLETE daily_news=ready saves=${saves.count}`);
} finally {
  database.close();
}
