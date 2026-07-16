param(
    [string]$CsvPath = "data/source/kbo_2025_final_roster.csv",
    [string]$DatabasePath = "data/players.db"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# 기존 가져오기 스크립트의 검증된 Windows SQLite 바인딩을 재사용한다.
if (-not ("WinSqlite" -as [type])) {
    $bootstrap = Get-Content -Raw -Encoding UTF8 "scripts/import_kbo_roster_db.ps1"
    & ([scriptblock]::Create($bootstrap)) -DatabasePath $DatabasePath
}

function ConvertTo-SqlText {
    param([AllowNull()][string]$Value)
    if ($null -eq $Value) { return "NULL" }
    return "'" + $Value.Replace("'", "''") + "'"
}

function ConvertTo-SqlInteger {
    param([AllowNull()][string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return "NULL" }
    return [int]$Value
}

$resolvedCsv = (Resolve-Path $CsvPath).Path
$resolvedDatabase = (Resolve-Path $DatabasePath).Path
$rows = @(Import-Csv -Encoding UTF8 $resolvedCsv)
if ($rows.Count -ne 636) { throw "Expected 636 final roster rows, got $($rows.Count)." }
if (@($rows.kbo_player_id | Sort-Object -Unique).Count -ne 636) { throw "KBO player IDs are not unique." }
if (@($rows | Where-Object { -not $_.birth_date }).Count -ne 0) { throw "A birth date is missing." }
if (@($rows.team | Sort-Object -Unique).Count -ne 10) { throw "Expected 10 teams." }

$alreadyImported = [WinSqlite]::Scalar(
    $resolvedDatabase,
    "SELECT version FROM roster_imports WHERE version='kbo-2025-10-31-v1'"
)
if ($alreadyImported -eq "kbo-2025-10-31-v1") {
    Write-Output "Final roster import already applied: $alreadyImported"
    return
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path (Split-Path -Parent $resolvedDatabase) "players.before-final-$timestamp.db"
Copy-Item -LiteralPath $resolvedDatabase -Destination $backupPath

$sql = [System.Text.StringBuilder]::new()
[void]$sql.AppendLine("BEGIN IMMEDIATE;")
[void]$sql.AppendLine(@"
DROP TABLE IF EXISTS final_roster_staging;
CREATE TEMP TABLE final_roster_staging (
    player_uid TEXT PRIMARY KEY,
    kbo_player_id TEXT UNIQUE NOT NULL,
    snapshot_date TEXT NOT NULL,
    team TEXT NOT NULL,
    name TEXT NOT NULL,
    old_name TEXT NOT NULL,
    position_group TEXT NOT NULL,
    position_name TEXT NOT NULL,
    age INTEGER NOT NULL,
    birth_date TEXT NOT NULL,
    bats_throws TEXT NOT NULL,
    height_cm INTEGER,
    weight_kg INTEGER,
    career TEXT NOT NULL,
    is_rookie INTEGER NOT NULL,
    is_foreign INTEGER NOT NULL,
    source_note TEXT NOT NULL,
    source_url TEXT NOT NULL
);
"@)

foreach ($row in $rows) {
    $oldName = if ($row.name -eq "배제성") { "배재성" } else { $row.name }
    $values = @(
        (ConvertTo-SqlText $row.player_uid),
        (ConvertTo-SqlText $row.kbo_player_id),
        (ConvertTo-SqlText $row.snapshot_date),
        (ConvertTo-SqlText $row.team),
        (ConvertTo-SqlText $row.name),
        (ConvertTo-SqlText $oldName),
        (ConvertTo-SqlText $row.position_group),
        (ConvertTo-SqlText $row.position_name),
        [int]$row.age,
        (ConvertTo-SqlText $row.birth_date),
        (ConvertTo-SqlText $row.bats_throws),
        (ConvertTo-SqlInteger $row.height_cm),
        (ConvertTo-SqlInteger $row.weight_kg),
        (ConvertTo-SqlText $row.career),
        [int]$row.is_rookie,
        [int]$row.is_foreign,
        (ConvertTo-SqlText $row.source_note),
        (ConvertTo-SqlText $row.source_url)
    ) -join ","
    [void]$sql.AppendLine("INSERT INTO final_roster_staging VALUES ($values);")
}

[void]$sql.AppendLine(@"
DROP TABLE IF EXISTS players_import;
CREATE TABLE players_import (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_uid TEXT UNIQUE,
    kbo_player_id TEXT UNIQUE NOT NULL,
    team TEXT NOT NULL,
    name TEXT NOT NULL,
    pos TEXT NOT NULL,
    age INTEGER NOT NULL,
    birth_date TEXT NOT NULL,
    bats_throws TEXT DEFAULT '',
    height_cm INTEGER,
    weight_kg INTEGER,
    career TEXT DEFAULT '',
    con INTEGER NOT NULL,
    pow INTEGER NOT NULL,
    eye INTEGER NOT NULL,
    def INTEGER NOT NULL,
    status INTEGER DEFAULT 1,
    lineup_pos INTEGER DEFAULT 0,
    role TEXT DEFAULT '선수',
    salary INTEGER DEFAULT 5000,
    snapshot_date TEXT,
    position_group TEXT,
    is_rookie INTEGER NOT NULL DEFAULT 0,
    is_foreign INTEGER NOT NULL DEFAULT 0,
    profile_complete INTEGER NOT NULL DEFAULT 0,
    source_note TEXT DEFAULT '',
    source_url TEXT DEFAULT ''
);

INSERT INTO players_import (
    player_uid, kbo_player_id, team, name, pos, age, birth_date, bats_throws,
    height_cm, weight_kg, career, con, pow, eye, def, status, lineup_pos, role,
    salary, snapshot_date, position_group, is_rookie, is_foreign,
    profile_complete, source_note, source_url
)
SELECT o.player_uid, o.kbo_player_id, o.team, o.name,
       COALESCE(p.pos, o.position_group), o.age, o.birth_date, o.bats_throws,
       o.height_cm, o.weight_kg, o.career,
       COALESCE(p.con, 50), COALESCE(p.pow, 50), COALESCE(p.eye, 50), COALESCE(p.def, 50),
       COALESCE(p.status, 0), COALESCE(p.lineup_pos, 0), COALESCE(p.role, '선수'),
       COALESCE(p.salary, 3000), o.snapshot_date, o.position_group,
       o.is_rookie, o.is_foreign, 1, o.source_note, o.source_url
FROM final_roster_staging o
LEFT JOIN players p ON p.id = (
    SELECT p2.id FROM players p2
    WHERE p2.name = o.old_name
      AND (
          (SELECT COUNT(*) FROM players px WHERE px.name = o.old_name) = 1
          OR p2.team = o.team
      )
    LIMIT 1
);

DROP TABLE players;
ALTER TABLE players_import RENAME TO players;
CREATE INDEX idx_players_team ON players(team);
CREATE UNIQUE INDEX idx_players_uid ON players(player_uid);
CREATE UNIQUE INDEX idx_players_kbo_id ON players(kbo_player_id);

INSERT INTO roster_imports (version, snapshot_date, player_count, source_path)
VALUES ('kbo-2025-10-31-v1', '2025-10-31', 636, $(ConvertTo-SqlText $resolvedCsv));
COMMIT;
"@)

try {
    [WinSqlite]::Exec($resolvedDatabase, $sql.ToString())
}
catch {
    Write-Error "Final roster import failed. Backup: $backupPath. $($_.Exception.Message)"
    throw
}

$checks = [ordered]@{
    players = [WinSqlite]::Scalar($resolvedDatabase, "SELECT COUNT(*) FROM players")
    teams = [WinSqlite]::Scalar($resolvedDatabase, "SELECT COUNT(DISTINCT team) FROM players")
    ids = [WinSqlite]::Scalar($resolvedDatabase, "SELECT COUNT(DISTINCT kbo_player_id) FROM players")
    birthdays = [WinSqlite]::Scalar($resolvedDatabase, "SELECT COUNT(*) FROM players WHERE birth_date <> ''")
    complete = [WinSqlite]::Scalar($resolvedDatabase, "SELECT COUNT(*) FROM players WHERE profile_complete = 1")
    integrity = [WinSqlite]::Scalar($resolvedDatabase, "PRAGMA integrity_check")
}
if ($checks.players -ne "636" -or $checks.teams -ne "10" -or $checks.ids -ne "636" -or
    $checks.birthdays -ne "636" -or $checks.complete -ne "636" -or $checks.integrity -ne "ok") {
    throw "Post-import validation failed: $($checks | ConvertTo-Json -Compress)"
}

Write-Output "IMPORT COMPLETE: $($checks | ConvertTo-Json -Compress)"
Write-Output "DATABASE: $resolvedDatabase"
Write-Output "BACKUP: $backupPath"
