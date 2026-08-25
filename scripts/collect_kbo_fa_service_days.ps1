param(
    [string]$CareerHistory = "data/source/kbo_player_career_history.csv",
    [string]$Output = "data/source/kbo_player_registration_days.csv",
    [int]$WorkerCount = 8
)

$ErrorActionPreference = "Stop"
$ids = Import-Csv $CareerHistory |
    Select-Object -ExpandProperty kbo_player_id -Unique |
    Where-Object { $_ -match '^\d+$' }

$buckets = @()
for ($index = 0; $index -lt $WorkerCount; $index++) {
    $buckets += ,@()
}
for ($index = 0; $index -lt $ids.Count; $index++) {
    $buckets[$index % $WorkerCount] += $ids[$index]
}

$jobs = foreach ($bucket in $buckets) {
    Start-Job -ArgumentList (, $bucket) -ScriptBlock {
        param($PlayerIds)
        $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
        $headers = @{
            "Referer" = "https://www.koreabaseball.com/Record/Player/PitcherDetail/SeasonReg.aspx"
            "X-Requested-With" = "XMLHttpRequest"
            "Accept" = "application/json, text/javascript, */*; q=0.01"
        }
        if ($PlayerIds.Count -gt 0) {
            Invoke-WebRequest -UseBasicParsing -WebSession $session `
                "https://www.koreabaseball.com/Record/Player/PitcherDetail/SeasonReg.aspx?playerId=$($PlayerIds[0])" |
                Out-Null
        }
        foreach ($playerId in $PlayerIds) {
            try {
                $response = Invoke-WebRequest -UseBasicParsing -WebSession $session -Method Post `
                    -Headers $headers -ContentType "application/x-www-form-urlencoded; charset=UTF-8" `
                    -Uri "https://www.koreabaseball.com/ws/Record.asmx/GetSeasonReg" `
                    -Body "pId=$playerId"
                $json = [Text.Encoding]::UTF8.GetString($response.RawContentStream.ToArray()) |
                    ConvertFrom-Json
                foreach ($entry in $json.rows) {
                    $cells = $entry.row
                    $season = [int]$cells[1].Text
                    if ($season -gt 2025) { continue }
                    $nationalText = [string]$cells[3].Text
                    $nationalDays = 0
                    $matches = [regex]::Matches($nationalText, '(?<![A-Za-z])(\d+)(?=\s*(?:\(|,|$))')
                    foreach ($match in $matches) {
                        $nationalDays += [int]$match.Groups[1].Value
                    }
                    [pscustomobject]@{
                        kbo_player_id = [string]$playerId
                        team = [string]$cells[0].Text
                        season = $season
                        registration_days = [int]$cells[2].Text
                        national_team = $nationalText
                        national_team_days = $nationalDays
                        snapshot_date = (Get-Date).ToString("yyyy-MM-dd")
                        source_url = "https://www.koreabaseball.com/Record/Player/PitcherDetail/SeasonReg.aspx?playerId=$playerId"
                    }
                }
            }
            catch {
                Write-Warning "등록일수 수집 실패: $playerId - $($_.Exception.Message)"
            }
        }
    }
}

$rows = $jobs | Wait-Job | Receive-Job
$jobs | Remove-Job -Force
$rows |
    Sort-Object @{ Expression = { [int]$_.kbo_player_id } }, season |
    Select-Object kbo_player_id, team, season, registration_days, national_team, national_team_days, snapshot_date, source_url |
    Export-Csv -Path $Output -NoTypeInformation -Encoding UTF8

Write-Host "수집 완료: $($rows.Count)개 시즌 -> $Output"
