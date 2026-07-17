param(
    [string]$RosterPath = "data/source/kbo_2025_final_roster.csv",
    [string]$ManifestPath = "data/source/player_photo_manifest.csv"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$roster = @(Import-Csv -Encoding UTF8 -LiteralPath $RosterPath)
if ($roster.Count -ne 636) {
    throw "Expected 636 roster rows, got $($roster.Count)"
}
if (@($roster.kbo_player_id | Sort-Object -Unique).Count -ne 636) {
    throw "Roster KBO player IDs must be unique"
}

$existingById = @{}
if (Test-Path -LiteralPath $ManifestPath) {
    foreach ($row in @(Import-Csv -Encoding UTF8 -LiteralPath $ManifestPath)) {
        if ($row.kbo_player_id) { $existingById[[string]$row.kbo_player_id] = $row }
    }
}

$output = foreach ($player in $roster | Sort-Object team, name, kbo_player_id) {
    $id = [string]$player.kbo_player_id
    $old = if ($existingById.ContainsKey($id)) { $existingById[$id] } else { $null }
    [pscustomobject][ordered]@{
        kbo_player_id = $id
        player_name = $player.name
        source_page_url = if ($null -ne $old) { $old.source_page_url } else { "" }
        image_url = if ($null -ne $old) { $old.image_url } else { "" }
        credit = if ($null -ne $old) { $old.credit } else { "" }
        license = if ($null -ne $old) { $old.license } else { "" }
        redistributable = if ($null -ne $old) { $old.redistributable } else { "0" }
        approved = if ($null -ne $old) { $old.approved } else { "0" }
        local_filename = if ($null -ne $old) { $old.local_filename } else { "" }
        status = if ($null -ne $old -and $old.status) { $old.status } else { "pending" }
        notes = if ($null -ne $old) { $old.notes } else { "" }
    }
}

$output | Export-Csv -NoTypeInformation -Encoding UTF8 -LiteralPath $ManifestPath
Write-Output "COMPLETE manifest_rows=$($output.Count) preserved=$($existingById.Count) path=$ManifestPath"
