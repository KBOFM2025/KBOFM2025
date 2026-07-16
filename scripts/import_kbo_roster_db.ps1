param(
    [string]$CsvPath = "data/source/kbo_2025_opening_roster.csv",
    [string]$DatabasePath = "data/players.db"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not ("WinSqlite" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class WinSqlite
{
    private const int SQLITE_ROW = 100;

    [DllImport("winsqlite3.dll", CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Unicode)]
    private static extern int sqlite3_open16(string filename, out IntPtr db);

    [DllImport("winsqlite3.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern int sqlite3_close(IntPtr db);

    [DllImport("winsqlite3.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr sqlite3_errmsg(IntPtr db);

    [DllImport("winsqlite3.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern int sqlite3_exec(IntPtr db, IntPtr sql, IntPtr callback, IntPtr arg, out IntPtr error);

    [DllImport("winsqlite3.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern void sqlite3_free(IntPtr pointer);

    [DllImport("winsqlite3.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern int sqlite3_prepare_v2(IntPtr db, IntPtr sql, int byteCount, out IntPtr statement, IntPtr tail);

    [DllImport("winsqlite3.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern int sqlite3_step(IntPtr statement);

    [DllImport("winsqlite3.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr sqlite3_column_text(IntPtr statement, int column);

    [DllImport("winsqlite3.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern int sqlite3_finalize(IntPtr statement);

    private static IntPtr Utf8(string value)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(value + "\0");
        IntPtr pointer = Marshal.AllocHGlobal(bytes.Length);
        Marshal.Copy(bytes, 0, pointer, bytes.Length);
        return pointer;
    }

    private static string Utf8String(IntPtr pointer)
    {
        if (pointer == IntPtr.Zero) return null;
        int length = 0;
        while (Marshal.ReadByte(pointer, length) != 0) length++;
        byte[] bytes = new byte[length];
        Marshal.Copy(pointer, bytes, 0, length);
        return Encoding.UTF8.GetString(bytes);
    }

    public static void Exec(string path, string sql)
    {
        IntPtr db;
        int rc = sqlite3_open16(path, out db);
        if (rc != 0) throw new InvalidOperationException("SQLite open failed: " + rc);
        IntPtr sqlPointer = Utf8(sql);
        IntPtr error = IntPtr.Zero;
        try
        {
            rc = sqlite3_exec(db, sqlPointer, IntPtr.Zero, IntPtr.Zero, out error);
            if (rc != 0)
            {
                string message = error != IntPtr.Zero ? Utf8String(error) : Utf8String(sqlite3_errmsg(db));
                throw new InvalidOperationException("SQLite error " + rc + ": " + message);
            }
        }
        finally
        {
            if (error != IntPtr.Zero) sqlite3_free(error);
            Marshal.FreeHGlobal(sqlPointer);
            sqlite3_close(db);
        }
    }

    public static string Scalar(string path, string sql)
    {
        IntPtr db;
        int rc = sqlite3_open16(path, out db);
        if (rc != 0) throw new InvalidOperationException("SQLite open failed: " + rc);
        IntPtr sqlPointer = Utf8(sql);
        IntPtr statement = IntPtr.Zero;
        try
        {
            rc = sqlite3_prepare_v2(db, sqlPointer, -1, out statement, IntPtr.Zero);
            if (rc != 0) throw new InvalidOperationException("SQLite prepare failed: " + Utf8String(sqlite3_errmsg(db)));
            rc = sqlite3_step(statement);
            return rc == SQLITE_ROW ? Utf8String(sqlite3_column_text(statement, 0)) : null;
        }
        finally
        {
            if (statement != IntPtr.Zero) sqlite3_finalize(statement);
            Marshal.FreeHGlobal(sqlPointer);
            sqlite3_close(db);
        }
    }
}
"@
}

function ConvertTo-SqlText {
    param([AllowNull()][string]$Value)
    if ($null -eq $Value) { return "NULL" }
    return "'" + $Value.Replace("'", "''") + "'"
}

$resolvedCsv = (Resolve-Path $CsvPath).Path
$resolvedDatabase = (Resolve-Path $DatabasePath).Path
$rows = @(Import-Csv -Encoding UTF8 $resolvedCsv)
if ($rows.Count -ne 597) {
    throw "Expected 597 official roster rows, got $($rows.Count)."
}

$historyExists = [WinSqlite]::Scalar(
    $resolvedDatabase,
    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='roster_imports'"
)
$alreadyImported = if ($historyExists -eq "1") {
    [WinSqlite]::Scalar(
        $resolvedDatabase,
        "SELECT version FROM roster_imports WHERE version='kbo-2025-02-10-v1'"
    )
}
else {
    $null
}
if ($alreadyImported -eq "kbo-2025-02-10-v1") {
    Write-Output "Roster import already applied: $alreadyImported"
    return
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path (Split-Path -Parent $resolvedDatabase) "players.before-roster-$timestamp.db"
Copy-Item -LiteralPath $resolvedDatabase -Destination $backupPath

$sql = [System.Text.StringBuilder]::new()
[void]$sql.AppendLine("BEGIN IMMEDIATE;")
[void]$sql.AppendLine("DROP TABLE IF EXISTS official_roster_staging;")
[void]$sql.AppendLine(@"
CREATE TEMP TABLE official_roster_staging (
    player_uid TEXT PRIMARY KEY,
    snapshot_date TEXT NOT NULL,
    team TEXT NOT NULL,
    name TEXT NOT NULL,
    position_group TEXT NOT NULL,
    is_rookie INTEGER NOT NULL,
    is_foreign INTEGER NOT NULL,
    source_note TEXT NOT NULL,
    source_url TEXT NOT NULL
);
"@)

foreach ($row in $rows) {
    $uid = "KBO-2025-S$($row.source_sheet)-$($row.source_cell)"
    $values = @(
        (ConvertTo-SqlText $uid),
        (ConvertTo-SqlText $row.snapshot_date),
        (ConvertTo-SqlText $row.team),
        (ConvertTo-SqlText $row.name),
        (ConvertTo-SqlText $row.position_group),
        [int]$row.is_rookie,
        [int]$row.is_foreign,
        (ConvertTo-SqlText $row.note),
        (ConvertTo-SqlText $row.source)
    ) -join ","
    [void]$sql.AppendLine("INSERT INTO official_roster_staging VALUES ($values);")
}

[void]$sql.AppendLine(@"
DROP TABLE IF EXISTS players_import;
CREATE TABLE players_import (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_uid TEXT UNIQUE,
    team TEXT NOT NULL,
    name TEXT NOT NULL,
    pos TEXT NOT NULL,
    age INTEGER NOT NULL,
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
    player_uid, team, name, pos, age, con, pow, eye, def,
    status, lineup_pos, role, salary, snapshot_date, position_group,
    is_rookie, is_foreign, profile_complete, source_note, source_url
)
SELECT
    o.player_uid,
    o.team,
    o.name,
    COALESCE(p.pos, o.position_group),
    COALESCE(p.age, 25),
    COALESCE(p.con, 50),
    COALESCE(p.pow, 50),
    COALESCE(p.eye, 50),
    COALESCE(p.def, 50),
    COALESCE(p.status, 0),
    COALESCE(p.lineup_pos, 0),
    COALESCE(p.role, '미지정'),
    COALESCE(p.salary, 3000),
    o.snapshot_date,
    o.position_group,
    o.is_rookie,
    o.is_foreign,
    0,
    o.source_note,
    o.source_url
FROM official_roster_staging AS o
LEFT JOIN players AS p
  ON p.team = o.team
 AND p.name = o.name
 AND (SELECT COUNT(*) FROM official_roster_staging s
      WHERE s.team = o.team AND s.name = o.name) = 1
 AND (SELECT COUNT(*) FROM players x
      WHERE x.team = p.team AND x.name = p.name) = 1;

DROP TABLE players;
ALTER TABLE players_import RENAME TO players;
CREATE INDEX idx_players_team ON players(team);
CREATE UNIQUE INDEX idx_players_uid ON players(player_uid);

CREATE TABLE IF NOT EXISTS roster_imports (
    version TEXT PRIMARY KEY,
    snapshot_date TEXT NOT NULL,
    player_count INTEGER NOT NULL,
    source_path TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO roster_imports (version, snapshot_date, player_count, source_path)
VALUES ('kbo-2025-02-10-v1', '2025-02-10', 597, $(ConvertTo-SqlText $resolvedCsv));
COMMIT;
"@)

try {
    [WinSqlite]::Exec($resolvedDatabase, $sql.ToString())
}
catch {
    Write-Error "Roster import failed. The untouched backup is at $backupPath. $($_.Exception.Message)"
    throw
}

$total = [WinSqlite]::Scalar($resolvedDatabase, "SELECT COUNT(*) FROM players")
$teams = [WinSqlite]::Scalar($resolvedDatabase, "SELECT COUNT(DISTINCT team) FROM players")
$uids = [WinSqlite]::Scalar($resolvedDatabase, "SELECT COUNT(DISTINCT player_uid) FROM players")
if ($total -ne "597" -or $teams -ne "10" -or $uids -ne "597") {
    throw "Post-import validation failed: players=$total teams=$teams uids=$uids"
}

Write-Output "IMPORT COMPLETE: players=$total teams=$teams unique_uids=$uids"
Write-Output "DATABASE: $resolvedDatabase"
Write-Output "BACKUP: $backupPath"
