import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = (...parts) => path.join(root, "data", "source", ...parts);
const outputPath = source("kbo_2025_hitter_abilities.csv");
const formulaVersion = "kbo-hitter-abilities-v7-cross-role-calibrated";

function parseCsv(text) {
  const records = [];
  let record = [], field = "", quoted = false;
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
      if (record.some((value) => value !== "")) records.push(record);
      record = []; field = "";
    } else field += character;
  }
  if (field !== "" || record.length) {
    record.push(field.replace(/\r$/, ""));
    records.push(record);
  }
  const headers = records.shift().map((header) => header.replace(/^\uFEFF/, ""));
  return records.map((values) =>
    Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])));
}

function load(name) {
  return parseCsv(fs.readFileSync(source(name), "utf8"));
}

function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function optionalNumber(value) {
  const parsed = Number(value);
  return value !== "" && value !== "N/A" && Number.isFinite(parsed) ? parsed : null;
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function mean(values, fallback = 0.5) {
  const usable = values.filter(Number.isFinite);
  return usable.length ? usable.reduce((sum, value) => sum + value, 0) / usable.length : fallback;
}

function percentile(values, target, higherIsBetter = true) {
  const usable = values.filter(Number.isFinite).sort((left, right) => left - right);
  if (!usable.length || !Number.isFinite(target)) return 0.5;
  let below = 0, equal = 0;
  for (const value of usable) {
    if (value < target) below += 1;
    else if (Math.abs(value - target) < 1e-10) equal += 1;
  }
  const result = (below + 0.5 * equal) / usable.length;
  return higherIsBetter ? result : 1 - result;
}

function reliability(sample, stabilization) {
  return clamp(sample / (sample + stabilization), 0, 1);
}

function ratingFromPercentile(rawPercentile, sampleReliability, level) {
  const regressed = 0.5 + (clamp(rawPercentile, 0, 1) - 0.5) * sampleReliability;
  const center = level === "KBO" ? 11 : level === "FUTURES" ? 8.5 : 8;
  const spread = level === "KBO" ? 16 : level === "FUTURES" ? 12 : 8;
  return clamp(Math.round(center + spread * (regressed - 0.5)), 1, 20);
}

function innings(value) {
  const text = String(value ?? "").trim();
  if (!text) return 0;
  const [whole, fraction] = text.split(/\s+/);
  const base = number(whole);
  if (fraction === "1/3") return base + 1 / 3;
  if (fraction === "2/3") return base + 2 / 3;
  return base;
}

function groupBy(rows, key) {
  const result = new Map();
  for (const row of rows) {
    const value = String(row[key] ?? "");
    if (!result.has(value)) result.set(value, []);
    result.get(value).push(row);
  }
  return result;
}

function csvCell(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

const baseRows = load("kbo_2025_hitter_abilities.csv");
const rosterRows = load("kbo_2025_final_roster.csv");
const firstRows = load("kbo_2025_first_team_hitting.csv");
const futuresRows = load("kbo_2025_futures_hitting.csv");
const runningRows = load("kbo_2025_running.csv");
const splitRows = load("kbo_2025_hitter_situation_splits.csv");
const defenseRows = load("kbo_2025_defense.csv");
const salaryRows = load("kbo_2025_verified_hitter_salaries.csv");
const advancedRows = load("kbo_2025_advanced_hitter_metrics.csv");
const pitcherRows = load("kbo_2025_pitcher_abilities.csv");

if (baseRows.length !== 317) throw new Error(`Expected 317 hitters, got ${baseRows.length}`);

const byId = (rows) => new Map(rows.map((row) => [String(row.kbo_player_id), row]));
const firstById = byId(firstRows);
const futuresById = byId(futuresRows);
const runningById = byId(runningRows);
const salaryById = byId(salaryRows);
const defenseById = groupBy(defenseRows, "kbo_player_id");
const splitsById = groupBy(
  splitRows.filter((row) => row.split_category === "pitcher_type"),
  "kbo_player_id",
);
const advancedByName = groupBy(advancedRows, "player_name");
const rosterById = byId(rosterRows);
const rosterNameCounts = new Map();
for (const row of baseRows) {
  rosterNameCounts.set(row.player_name, (rosterNameCounts.get(row.player_name) ?? 0) + 1);
}

function matchAdvanced(row) {
  const candidates = advancedByName.get(row.player_name) ?? [];
  if (!candidates.length) return null;
  const officialPa = number(firstById.get(String(row.kbo_player_id))?.PA);
  if (candidates.length === 1 && (rosterNameCounts.get(row.player_name) ?? 0) > 1) {
    const candidate = candidates[0];
    if (number(candidate.PA) !== officialPa && candidate.source_team !== row.snapshot_team) return null;
  }
  return [...candidates].sort((left, right) => {
    const score = (candidate) => {
      let value = -Math.abs(number(candidate.PA) - officialPa) * 2;
      if (number(candidate.PA) === officialPa) value += 1000;
      if (candidate.source_team === row.snapshot_team) value += 100;
      if (candidate.position === row.position_group) value += 10;
      return value;
    };
    return score(right) - score(left);
  })[0];
}

const models = baseRows.map((base) => {
  const id = String(base.kbo_player_id);
  const first = firstById.get(id);
  const futures = futuresById.get(id);
  const firstPa = number(first?.PA);
  const futuresPa = number(futures?.PA);
  const level = firstPa > 0 ? "KBO" : futuresPa > 0 ? "FUTURES" : "none";
  const record = level === "KBO" ? first : level === "FUTURES" ? futures : null;
  const pa = number(record?.PA);
  const ab = Math.max(1, number(record?.AB));
  const advanced = level === "KBO" ? matchAdvanced(base) : null;
  const running = runningById.get(id);
  const timesOnBase = Math.max(1, number(record?.H) + number(record?.BB) + number(record?.HBP));
  return {
    id, base, first, futures, record, advanced, running, level, pa, ab,
    avg: number(record?.AVG),
    iso: Math.max(0, number(record?.SLG) - number(record?.AVG)),
    hrRate: number(record?.HR) / Math.max(1, pa),
    xbhRate: (number(record?.["2B"]) + 2 * number(record?.["3B"]) + 3 * number(record?.HR)) / ab,
    bbRate: number(record?.BB) / Math.max(1, pa),
    kRate: number(record?.SO) / Math.max(1, pa),
    bbToK: number(record?.BB) / Math.max(1, number(record?.SO)),
    obpGap: Math.max(0, number(record?.OBP) - number(record?.AVG)),
    gdpRate: number(record?.GDP) / Math.max(1, ab),
    attemptRate: number(running?.SBA) / timesOnBase,
    tripleRate: number(record?.["3B"]) / ab,
    sbRate: number(running?.SB) / Math.max(1, number(running?.SBA)),
    outRate: number(running?.OOB) / timesOnBase,
    pickoffRate: number(running?.PKO) / timesOnBase,
    advancedBabip: optionalNumber(advanced?.BABIP),
    advancedWrc: optionalNumber(advanced?.wRC_plus),
    advancedSfr: optionalNumber(advanced?.SFR),
    advancedWar: optionalNumber(advanced?.WAR),
  };
});

const cohorts = {
  KBO: models.filter((model) => model.level === "KBO"),
  FUTURES: models.filter((model) => model.level === "FUTURES"),
};

function metricPercentile(model, field, higherIsBetter = true) {
  const cohort = cohorts[model.level] ?? [];
  return percentile(cohort.map((item) => item[field]), model[field], higherIsBetter);
}

const splitOpsByLabel = new Map();
for (const split of splitRows.filter((row) => row.split_category === "pitcher_type")) {
  const ab = number(split.AB);
  if (ab <= 0) continue;
  const hits = number(split.H), doubles = number(split["2B"]);
  const triples = number(split["3B"]), homers = number(split.HR);
  const totalBases = hits + doubles + 2 * triples + 3 * homers;
  const obp = (hits + number(split.BB) + number(split.HBP)) /
    Math.max(1, ab + number(split.BB) + number(split.HBP));
  const ops = obp + totalBases / ab;
  if (!splitOpsByLabel.has(split.split_label)) splitOpsByLabel.set(split.split_label, []);
  splitOpsByLabel.get(split.split_label).push(ops);
}

function timingPercentile(model) {
  const rows = splitsById.get(model.id) ?? [];
  const parts = [];
  let sample = 0;
  for (const row of rows) {
    const ab = number(row.AB);
    if (ab <= 0) continue;
    const hits = number(row.H), doubles = number(row["2B"]);
    const triples = number(row["3B"]), homers = number(row.HR);
    const totalBases = hits + doubles + 2 * triples + 3 * homers;
    const obp = (hits + number(row.BB) + number(row.HBP)) /
      Math.max(1, ab + number(row.BB) + number(row.HBP));
    const ops = obp + totalBases / ab;
    parts.push(percentile(splitOpsByLabel.get(row.split_label) ?? [], ops));
    sample += ab;
  }
  if (!parts.length) return { percentile: 0.5, sample: 0 };
  const average = mean(parts);
  const deviation = Math.sqrt(mean(parts.map((value) => (value - average) ** 2), 0));
  return { percentile: clamp(average - deviation * 0.12, 0, 1), sample };
}

const dominantDefense = new Map();
const defenseModels = [];
for (const model of models) {
  const rows = defenseById.get(model.id) ?? [];
  if (!rows.length) continue;
  const summarized = rows.map((row) => {
    const ip = innings(row.IP);
    const chances = number(row.PO) + number(row.A) + number(row.E);
    return {
      position: row.defense_position,
      ip,
      rangeRate: (number(row.PO) + number(row.A)) * 9 / Math.max(1, ip),
      assistRate: number(row.A) * 9 / Math.max(1, ip),
      dpRate: number(row.DP) * 9 / Math.max(1, ip),
      accuracy: 1 - number(row.E) / Math.max(1, chances),
      catcherCs: optionalNumber(row.CS_PCT),
    };
  });
  const primary = [...summarized].sort((left, right) => right.ip - left.ip)[0];
  const totalIp = summarized.reduce((sum, row) => sum + row.ip, 0);
  const weighted = (field, fallback = 0) => totalIp
    ? summarized.reduce((sum, row) => sum + number(row[field], fallback) * row.ip, 0) / totalIp
    : fallback;
  const defense = {
    id: model.id,
    position: primary.position,
    ip: totalIp,
    rangeRate: weighted("rangeRate"),
    assistRate: weighted("assistRate"),
    dpRate: weighted("dpRate"),
    accuracy: weighted("accuracy", 0.97),
    catcherCs: mean(summarized.map((row) => row.catcherCs).filter(Number.isFinite), 0.5),
    advancedSfr: model.advancedSfr,
  };
  dominantDefense.set(model.id, defense);
  defenseModels.push(defense);
}
const defensesByPosition = groupBy(defenseModels, "position");

function defensePercentile(defense, field, higherIsBetter = true) {
  if (!defense) return 0.5;
  const peers = defensesByPosition.get(defense.position) ?? defenseModels;
  return percentile(peers.map((item) => item[field]), defense[field], higherIsBetter);
}

function salaryPrior(row) {
  const salary = number(salaryById.get(row.id)?.salary_10k_krw);
  if (!salary) return null;
  const foreign = salaryById.get(row.id)?.coverage === "foreign_contract_salary";
  const baseline = foreign ? 100000 : 16071;
  return clamp(10 + Math.log2(salary / baseline) * (foreign ? 0.8 : 1.25), 8, 15);
}

const output = models.map((model) => {
  const { base, level, pa } = model;
  const offReliability = level === "KBO"
    ? reliability(pa, 120)
    : level === "FUTURES" ? reliability(pa, 180) : 0;

  const avgPct = metricPercentile(model, "avg");
  const isoPct = metricPercentile(model, "iso");
  const hrPct = metricPercentile(model, "hrRate");
  const xbhPct = metricPercentile(model, "xbhRate");
  const bbPct = metricPercentile(model, "bbRate");
  const kGoodPct = metricPercentile(model, "kRate", false);
  const bbkPct = metricPercentile(model, "bbToK");
  const obpGapPct = metricPercentile(model, "obpGap");
  const gdpGoodPct = metricPercentile(model, "gdpRate", false);
  const wrcPct = model.advancedWrc == null
    ? 0.5
    : percentile(cohorts.KBO.map((item) => item.advancedWrc).filter(Number.isFinite), model.advancedWrc);
  const babipPct = model.advancedBabip == null
    ? 0.5
    : percentile(cohorts.KBO.map((item) => item.advancedBabip).filter(Number.isFinite), model.advancedBabip);

  const contactComposite = 0.55 * avgPct + 0.27 * kGoodPct + 0.10 * wrcPct + 0.08 * babipPct;
  const powerComposite = 0.55 * isoPct + 0.25 * hrPct + 0.15 * xbhPct + 0.05 * wrcPct;
  const eyeComposite = 0.65 * bbPct + 0.20 * bbkPct + 0.15 * obpGapPct;
  const timing = timingPercentile(model);
  const controlComposite = 0.55 * kGoodPct + 0.20 * avgPct + 0.15 * gdpGoodPct + 0.10 * timing.percentile;
  const timingComposite = 0.65 * timing.percentile + 0.20 * contactComposite + 0.15 * kGoodPct;

  const attemptPct = metricPercentile(model, "attemptRate");
  const triplePct = metricPercentile(model, "tripleRate");
  const speedComposite = 0.60 * attemptPct + 0.25 * triplePct +
    0.15 * metricPercentile(model, "sbRate");
  const runningSample = number(model.running?.SBA) + Math.min(60, pa / 10);
  const runningReliability = reliability(runningSample, 25);
  const judgmentComposite = 0.50 * metricPercentile(model, "sbRate") +
    0.30 * metricPercentile(model, "outRate", false) +
    0.20 * metricPercentile(model, "pickoffRate", false);

  let contact = ratingFromPercentile(contactComposite, offReliability, level);
  let power = ratingFromPercentile(powerComposite, offReliability, level);
  let plateDiscipline = ratingFromPercentile(eyeComposite, offReliability, level);
  let batControl = ratingFromPercentile(controlComposite, offReliability, level);
  let timingRating = ratingFromPercentile(
    timingComposite,
    Math.min(offReliability, reliability(timing.sample, 150)),
    level,
  );
  const speed = ratingFromPercentile(speedComposite, Math.max(offReliability * 0.7, runningReliability), level);
  const baserunningJudgment = ratingFromPercentile(judgmentComposite, runningReliability, level);

  const prior = salaryPrior(model);
  const skillMean = mean([contact, power, plateDiscipline, batControl, timingRating], 8);
  const marketSupport = prior == null
    ? 0
    : clamp(Math.round((prior - skillMean) * (1 - offReliability) * 0.35), -1, 1);
  contact = clamp(contact + marketSupport, 1, 20);
  power = clamp(power + marketSupport, 1, 20);
  plateDiscipline = clamp(plateDiscipline + marketSupport, 1, 20);
  batControl = clamp(batControl + marketSupport, 1, 20);
  timingRating = clamp(timingRating + marketSupport, 1, 20);

  const defense = dominantDefense.get(model.id);
  const defenseReliability = defense ? reliability(defense.ip, 400) : 0;
  const sfrPct = defense?.advancedSfr == null
    ? 0.5
    : percentile(
      defenseModels.filter((item) => item.advancedSfr != null).map((item) => item.advancedSfr),
      defense.advancedSfr,
    );
  const rangeComposite = 0.50 * defensePercentile(defense, "rangeRate") +
    0.35 * sfrPct + 0.15 * (speed / 20);
  const armComposite = defense?.position === "포수"
    ? 0.65 * defensePercentile(defense, "catcherCs") + 0.35 * defensePercentile(defense, "assistRate")
    : 0.75 * defensePercentile(defense, "assistRate") + 0.25 * defensePercentile(defense, "dpRate");
  const accuracyComposite = defensePercentile(defense, "accuracy");
  const judgmentDefenseComposite = 0.45 * sfrPct +
    0.30 * defensePercentile(defense, "dpRate") +
    0.25 * accuracyComposite;
  const defenseLevel = level === "none" ? "none" : level;
  const fieldingRange = ratingFromPercentile(rangeComposite, defenseReliability, defenseLevel);
  const throwingPower = ratingFromPercentile(armComposite, defenseReliability, defenseLevel);
  const throwingAccuracy = ratingFromPercentile(accuracyComposite, defenseReliability, defenseLevel);
  const fieldingJudgment = ratingFromPercentile(judgmentDefenseComposite, defenseReliability, defenseLevel);
  const catchingComposite = defense?.position === "포수"
    ? 0.50 * accuracyComposite + 0.30 * defensePercentile(defense, "catcherCs") +
      0.20 * defensePercentile(defense, "rangeRate")
    : 0.55 * accuracyComposite + 0.45 * defensePercentile(defense, "rangeRate");
  const catching = ratingFromPercentile(catchingComposite, defenseReliability, defenseLevel);

  const age = number(rosterById.get(model.id)?.age, 24);
  const regularBonus = pa >= 400 ? 2 : pa >= 200 ? 1 : 0;
  const salaryMental = prior == null ? 0 : clamp(Math.round((prior - 10) / 3), -1, 1);
  const composure = clamp(Math.round(
    0.30 * plateDiscipline + 0.25 * batControl + 0.20 * timingRating +
    0.15 * baserunningJudgment + 0.10 * fieldingJudgment + salaryMental,
  ), 1, 20);
  const leadership = clamp(Math.round(
    8 + clamp((age - 24) / 3, -2, 4) + regularBonus + salaryMental +
    (level === "FUTURES" ? -1 : 0),
  ), 1, 20);
  const aggressiveness = clamp(Math.round(
    0.35 * power + 0.25 * speed + 0.20 * baserunningJudgment +
    0.20 * (21 - plateDiscipline),
  ), 1, 20);

  const confidence = level === "KBO" && pa >= 300 && model.advanced ? "high"
    : level === "KBO" && pa >= 100 ? "medium"
      : level === "FUTURES" && pa >= 150 ? "medium"
        : pa >= 30 ? "low" : pa > 0 ? "very_low" : "none";
  const details = {
    level,
    PA: pa,
    reliability: Number(offReliability.toFixed(4)),
    advanced_match: Boolean(model.advanced),
    contact_components: { avgPct, kGoodPct, wrcPct, babipPct },
    power_components: { isoPct, hrPct, xbhPct, wrcPct },
    discipline_components: { bbPct, bbkPct, obpGapPct },
    defense: {
      position: defense?.position ?? "",
      innings: Number((defense?.ip ?? 0).toFixed(1)),
      SFR: model.advancedSfr,
    },
    salary_prior: prior,
    salary_support: marketSupport,
  };

  return {
    ...base,
    contact, power, plate_discipline: plateDiscipline, bat_control: batControl,
    timing: timingRating,
    bunt: clamp(number(base.bunt, 1), 1, 20),
    speed, baserunning_judgment: baserunningJudgment,
    fielding_range: fieldingRange, catching, throwing_power: throwingPower,
    throwing_accuracy: throwingAccuracy, fielding_judgment: fieldingJudgment,
    composure, leadership, aggressiveness,
    source_level: level,
    batting_confidence: confidence,
    running_confidence: runningReliability >= 0.6 ? "high" : runningReliability >= 0.35 ? "medium" : "low",
    formula_version: formulaVersion,
    remaining_formula_version: formulaVersion,
    advanced_public_player_id: model.advanced?.public_player_id ?? "",
    advanced_wrc_plus: model.advancedWrc ?? "",
    advanced_sfr: model.advancedSfr ?? "",
    advanced_war: model.advancedWar ?? "",
    advanced_source_url: model.advanced?.source_url ?? "",
    rating_confidence: confidence,
    rating_detail_json: JSON.stringify(details),
  };
});

// 타자와 투수의 1~20 척도가 같은 의미를 갖도록 집단별 백분위를 대응한다.
// 원지표로 계산한 타자 순위와 능력별 차이는 유지하고, 핵심 타격 5개만
// 같은 레벨(KBO/FUTURES)의 투수 핵심 5개 분포에 맞춘다.
const hitterCore = ["contact", "power", "plate_discipline", "bat_control", "timing"];
const pitcherCore = [
  "pitcher_stuff", "pitcher_command", "pitcher_movement",
  "pitcher_stamina", "pitcher_pitchability",
];
const coreAverage = (row, columns) =>
  columns.reduce((sum, column) => sum + number(row[column]), 0) / columns.length;
const quantile = (values, probability) => {
  const sorted = [...values].filter(Number.isFinite).sort((left, right) => left - right);
  if (!sorted.length) return 8;
  const index = clamp(probability, 0, 1) * (sorted.length - 1);
  const lower = Math.floor(index), upper = Math.ceil(index);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (index - lower);
};
const targetByLevel = new Map(
  ["KBO", "FUTURES"].map((level) => [
    level,
    pitcherRows
      .filter((row) => String(row.source_level).toUpperCase() === level)
      .map((row) => coreAverage(row, pitcherCore)),
  ]),
);

for (const level of ["KBO", "FUTURES"]) {
  const hitters = output.filter((row) => row.source_level === level);
  const rawAverages = hitters.map((row) => coreAverage(row, hitterCore));
  for (const hitter of hitters) {
    const before = coreAverage(hitter, hitterCore);
    const rank = percentile(rawAverages, before);
    const target = quantile(targetByLevel.get(level), rank);
    let remaining = Math.round(target * hitterCore.length) -
      hitterCore.reduce((sum, column) => sum + number(hitter[column]), 0);
    const priority = [...hitterCore].sort((left, right) =>
      remaining >= 0
        ? number(hitter[right]) - number(hitter[left])
        : number(hitter[left]) - number(hitter[right]));
    let cursor = 0, safety = 0;
    while (remaining !== 0 && safety < 200) {
      const column = priority[cursor % priority.length];
      const direction = remaining > 0 ? 1 : -1;
      const next = clamp(number(hitter[column]) + direction, 1, 20);
      if (next !== number(hitter[column])) {
        hitter[column] = next;
        remaining -= direction;
      }
      cursor += 1;
      safety += 1;
    }
    const detail = JSON.parse(hitter.rating_detail_json);
    detail.cross_role_calibration = {
      reference: `pitcher_${level.toLowerCase()}_core_5`,
      percentile: Number(rank.toFixed(4)),
      raw_core_average: Number(before.toFixed(2)),
      target_core_average: Number(target.toFixed(2)),
      calibrated_core_average: Number(coreAverage(hitter, hitterCore).toFixed(2)),
    };
    hitter.rating_detail_json = JSON.stringify(detail);
  }
}

const ids = new Set(output.map((row) => row.kbo_player_id));
if (ids.size !== 317 || ids.has("")) throw new Error("Hitter IDs must be present and unique");
const ratingColumns = [
  "contact", "power", "plate_discipline", "bat_control", "timing", "bunt",
  "speed", "baserunning_judgment", "fielding_range", "catching",
  "throwing_power", "throwing_accuracy", "fielding_judgment",
  "composure", "leadership", "aggressiveness",
];
for (const row of output) {
  for (const column of ratingColumns) {
    if (!Number.isInteger(row[column]) || row[column] < 1 || row[column] > 20) {
      throw new Error(`Invalid rating ${row.kbo_player_id} ${column}=${row[column]}`);
    }
  }
}

const extraColumns = [
  "advanced_public_player_id", "advanced_wrc_plus", "advanced_sfr", "advanced_war",
  "advanced_source_url", "rating_confidence", "rating_detail_json",
];
const columns = [...Object.keys(baseRows[0]), ...extraColumns.filter((column) => !(column in baseRows[0]))];
const csv = [
  columns.map(csvCell).join(","),
  ...output.map((row) => columns.map((column) => csvCell(row[column])).join(",")),
].join("\n") + "\n";
fs.writeFileSync(outputPath, csv, "utf8");

const levelCounts = Object.groupBy(output, (row) => row.source_level);
const advancedMatches = output.filter((row) => row.advanced_public_player_id).length;
console.log(
  `COMPLETE hitters=${output.length} KBO=${levelCounts.KBO?.length ?? 0}` +
  ` FUTURES=${levelCounts.FUTURES?.length ?? 0} none=${levelCounts.none?.length ?? 0}` +
  ` advanced=${advancedMatches} formula=${formulaVersion}`,
);
