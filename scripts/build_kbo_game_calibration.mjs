import fs from "node:fs";
import path from "node:path";

const input = process.argv[2] ?? "data/source/kbo_2024_2025_regular_season_games.csv";
const output = process.argv[3] ?? "data/config/kbo_game_engine_calibration.json";

const teamNames = {
  KIA: "KIA 타이거즈",
  삼성: "삼성 라이온즈",
  LG: "LG 트윈스",
  두산: "두산 베어스",
  KT: "KT 위즈",
  SSG: "SSG 랜더스",
  롯데: "롯데 자이언츠",
  한화: "한화 이글스",
  NC: "NC 다이노스",
  키움: "키움 히어로즈",
};

function parseCsvLine(line) {
  const fields = [];
  let value = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (char === '"') {
      if (quoted && line[index + 1] === '"') {
        value += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === "," && !quoted) {
      fields.push(value);
      value = "";
    } else {
      value += char;
    }
  }
  fields.push(value);
  return fields;
}

function readCsv(filePath) {
  const lines = fs.readFileSync(filePath, "utf8").replace(/^\uFEFF/, "").trim().split(/\r?\n/);
  const headers = parseCsvLine(lines[0]);
  return lines.slice(1).map((line) => Object.fromEntries(
    parseCsvLine(line).map((value, index) => [headers[index], value]),
  ));
}

const mean = (values) => values.reduce((sum, value) => sum + value, 0) / values.length;
const stddev = (values) => {
  const average = mean(values);
  return Math.sqrt(mean(values.map((value) => (value - average) ** 2)));
};
const rounded = (value, digits = 4) => Number(value.toFixed(digits));
const winRate = (wins, losses) => (wins + losses ? wins / (wins + losses) : 0.5);

function teamRows(games) {
  const rows = new Map();
  const add = (team, row) => {
    if (!rows.has(team)) rows.set(team, []);
    rows.get(team).push(row);
  };
  for (const game of games) {
    const away = Number(game.away_score);
    const home = Number(game.home_score);
    add(game.away_team, { runsFor: away, runsAgainst: home, home: false });
    add(game.home_team, { runsFor: home, runsAgainst: away, home: true });
  }
  return rows;
}

function summarizeTeam(rows) {
  const wins = rows.filter((row) => row.runsFor > row.runsAgainst).length;
  const losses = rows.filter((row) => row.runsFor < row.runsAgainst).length;
  const home = rows.filter((row) => row.home);
  const away = rows.filter((row) => !row.home);
  const oneRun = rows.filter((row) => Math.abs(row.runsFor - row.runsAgainst) === 1);
  const splitRate = (split) => winRate(
    split.filter((row) => row.runsFor > row.runsAgainst).length,
    split.filter((row) => row.runsFor < row.runsAgainst).length,
  );
  return {
    games: rows.length,
    wins,
    losses,
    draws: rows.length - wins - losses,
    win_pct: rounded(winRate(wins, losses)),
    runs_for_per_game: rounded(mean(rows.map((row) => row.runsFor))),
    runs_against_per_game: rounded(mean(rows.map((row) => row.runsAgainst))),
    runs_scored_stddev: rounded(stddev(rows.map((row) => row.runsFor))),
    home_win_pct: rounded(splitRate(home)),
    away_win_pct: rounded(splitRate(away)),
    one_run_win_pct: rounded(splitRate(oneRun)),
  };
}

function counter(values) {
  const result = {};
  for (const value of values) result[value] = (result[value] ?? 0) + 1;
  return Object.fromEntries(Object.entries(result).sort((a, b) => Number(a[0]) - Number(b[0])));
}

function summarizeLeague(games) {
  const scores = games.flatMap((game) => [Number(game.away_score), Number(game.home_score)]);
  const decisive = games.filter((game) => game.away_score !== game.home_score);
  return {
    games: games.length,
    runs_per_team_game: rounded(mean(scores)),
    runs_stddev: rounded(stddev(scores)),
    home_win_pct: rounded(
      decisive.filter((game) => Number(game.home_score) > Number(game.away_score)).length / decisive.length,
    ),
    draw_rate: rounded((games.length - decisive.length) / games.length),
    one_run_game_rate: rounded(
      games.filter((game) => Math.abs(Number(game.home_score) - Number(game.away_score)) === 1).length / games.length,
    ),
    shutout_team_game_rate: rounded(scores.filter((score) => score === 0).length / scores.length),
    score_distribution: counter(scores),
    absolute_run_difference_distribution: counter(
      games.map((game) => Math.abs(Number(game.home_score) - Number(game.away_score))),
    ),
  };
}

function favoriteResults(games, summaries) {
  let eligible = 0;
  let lost = 0;
  let strongEligible = 0;
  let strongLost = 0;
  for (const game of games) {
    const away = summaries[game.away_team].win_pct;
    const home = summaries[game.home_team].win_pct;
    const gap = Math.abs(away - home);
    if (gap < 0.05 || game.away_score === game.home_score) continue;
    const favoriteHome = home > away;
    const homeWon = Number(game.home_score) > Number(game.away_score);
    eligible += 1;
    if (favoriteHome !== homeWon) lost += 1;
    if (gap >= 0.15) {
      strongEligible += 1;
      if (favoriteHome !== homeWon) strongLost += 1;
    }
  }
  return {
    favorite_games: eligible,
    favorite_loss_rate: rounded(eligible ? lost / eligible : 0),
    strong_favorite_games: strongEligible,
    strong_favorite_loss_rate: rounded(strongEligible ? strongLost / strongEligible : 0),
  };
}

const games = readCsv(input);
const seasons = {};
for (const season of ["2024", "2025"]) {
  const seasonGames = games.filter((game) => game.season === season);
  if (seasonGames.length !== 720) throw new Error(`Expected 720 games for ${season}`);
  const summaries = Object.fromEntries(
    [...teamRows(seasonGames)].map(([team, rows]) => [team, summarizeTeam(rows)]),
  );
  seasons[season] = {
    league: { ...summarizeLeague(seasonGames), ...favoriteResults(seasonGames, summaries) },
    teams: Object.fromEntries(
      Object.entries(summaries).sort().map(([team, summary]) => [teamNames[team], summary]),
    ),
  };
}

const weights = { 2024: 0.4, 2025: 0.6 };
const combinedKeys = [
  "runs_per_team_game", "runs_stddev", "home_win_pct", "draw_rate",
  "one_run_game_rate", "shutout_team_game_rate", "favorite_loss_rate",
  "strong_favorite_loss_rate",
];
const combined = Object.fromEntries(combinedKeys.map((key) => [
  key,
  rounded(Object.entries(weights).reduce(
    (sum, [season, weight]) => sum + seasons[season].league[key] * weight,
    0,
  )),
]));
combined.season_weights = weights;
combined.day_form_rating_sd = rounded(Math.max(1.0, Math.min(2.6, 1.2 + combined.favorite_loss_rate * 3.2)));
combined.shared_run_environment_sd = rounded(Math.max(
  0.07,
  Math.min(0.16, (combined.runs_stddev / combined.runs_per_team_game - 0.55) * 0.45),
));

const payload = {
  schema_version: 1,
  scope: "KBO regular season",
  source: "KBO official schedule game results",
  source_url: "https://www.koreabaseball.com/Schedule/Schedule.aspx",
  seasons,
  combined,
};
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
console.log(
  `COMPLETE games=${games.length} output=${output} rpg=${combined.runs_per_team_game.toFixed(3)} favorite_loss=${combined.favorite_loss_rate.toFixed(3)}`,
);
