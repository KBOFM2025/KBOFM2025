param(
    [string]$ManifestPath = "data/source/player_photo_manifest.csv",
    [string]$OutputDirectory = "image/players/local"
)

$ErrorActionPreference = "Stop"
$rows = @(Import-Csv -Encoding UTF8 -LiteralPath $ManifestPath)
$completed = 0
foreach ($row in $rows) {
    $filename = "$($row.kbo_player_id).png"
    if (Test-Path -LiteralPath (Join-Path $OutputDirectory $filename)) {
        $row.local_filename = $filename
        $row.status = "background_removed"
        $row.notes = "KBO 공식 프로필 원본에서 로컬 인물 분할 처리; 투명 PNG; 배포 및 Git 제외"
        $completed++
    }
}
$rows | Export-Csv -NoTypeInformation -Encoding UTF8 -LiteralPath $ManifestPath
Write-Output "COMPLETE transparent=$completed total=$($rows.Count)"
