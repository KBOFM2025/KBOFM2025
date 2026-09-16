param(
    [int[]]$Seasons = @(2024, 2025),
    [string]$OutputPath = "data/source/kbo_2024_2025_regular_season_games.csv"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scheduleUri = "https://www.koreabaseball.com/ws/Schedule.asmx/GetScheduleList"
$schedulePage = "https://www.koreabaseball.com/Schedule/Schedule.aspx?form=MG0AV3"
$headers = @{
    Referer = $schedulePage
    "X-Requested-With" = "XMLHttpRequest"
}
function ConvertFrom-HtmlText {
    param([AllowEmptyString()][string]$Value)
    if ($null -eq $Value) { $Value = "" }
    $text = [regex]::Replace($Value, '<br\s*/?>', ' / ', 'IgnoreCase')
    $text = [regex]::Replace($text, '<[^>]+>', '')
    return [System.Net.WebUtility]::HtmlDecode($text).Trim()
}

function Get-CellByClass {
    param([object[]]$Cells, [string]$ClassName)
    return $Cells | Where-Object { [string]$_.Class -eq $ClassName } | Select-Object -First 1
}

$games = [System.Collections.Generic.List[object]]::new()
foreach ($season in $Seasons) {
    foreach ($month in 3..10) {
        $body = @{
            leId = "1"
            srIdList = "0,9,6"
            seasonId = [string]$season
            gameMonth = $month.ToString("00")
            teamId = ""
        }
        $response = Invoke-RestMethod -Method Post -Uri $scheduleUri -Headers $headers -Body $body
        foreach ($item in @($response.rows)) {
            $cells = @($item.row)
            $playCell = Get-CellByClass $cells "play"
            $relayCell = Get-CellByClass $cells "relay"
            $timeCell = Get-CellByClass $cells "time"
            if ($null -eq $playCell -or $null -eq $relayCell) { continue }

            $linkMatch = [regex]::Match(
                [string]$relayCell.Text,
                'gameDate=(\d{8})&(?:amp;)?gameId=([A-Za-z0-9]+)',
                'IgnoreCase'
            )
            if (-not $linkMatch.Success) { continue }

            $spans = @(
                [regex]::Matches([string]$playCell.Text, '<span(?:\s+class="[^"]*")?>(.*?)</span>', 'Singleline,IgnoreCase') |
                    ForEach-Object { ConvertFrom-HtmlText $_.Groups[1].Value }
            )
            if ($spans.Count -lt 5) { continue }
            $awayScore = 0
            $homeScore = 0
            if (-not [int]::TryParse($spans[1], [ref]$awayScore)) { continue }
            if (-not [int]::TryParse($spans[3], [ref]$homeScore)) { continue }

            $playIndex = [array]::IndexOf($cells, $playCell)
            $stadiumIndex = $playIndex + 5
            $stadium = if ($stadiumIndex -lt $cells.Count) {
                ConvertFrom-HtmlText ([string]$cells[$stadiumIndex].Text)
            } else { "" }
            $gameDate = $linkMatch.Groups[1].Value
            $games.Add([pscustomobject][ordered]@{
                season = $season
                game_date = ("{0}-{1}-{2}" -f $gameDate.Substring(0, 4), $gameDate.Substring(4, 2), $gameDate.Substring(6, 2))
                game_id = $linkMatch.Groups[2].Value
                start_time = if ($null -ne $timeCell) { ConvertFrom-HtmlText ([string]$timeCell.Text) } else { "" }
                away_team = $spans[0]
                away_score = $awayScore
                home_team = $spans[4]
                home_score = $homeScore
                stadium = $stadium
                source_url = "https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx?gameDate=$gameDate&gameId=$($linkMatch.Groups[2].Value)&section=REVIEW"
            })
        }
        Write-Host "SEASON=$season MONTH=$($month.ToString('00')) COLLECTED=$($games.Count)"
    }
}

$games = @($games | Sort-Object season, game_date, game_id -Unique)
foreach ($season in $Seasons) {
    $seasonGames = @($games | Where-Object season -eq $season)
    if ($seasonGames.Count -ne 720) {
        throw "Expected 720 completed regular-season games for $season, got $($seasonGames.Count)."
    }
    $teamCounts = @{}
    foreach ($game in $seasonGames) {
        foreach ($team in @($game.away_team, $game.home_team)) {
            if (-not $teamCounts.ContainsKey($team)) { $teamCounts[$team] = 0 }
            $teamCounts[$team]++
        }
    }
    if ($teamCounts.Count -ne 10) {
        throw "Expected 10 teams for $season, got $($teamCounts.Count)."
    }
    foreach ($entry in $teamCounts.GetEnumerator()) {
        if ($entry.Value -ne 144) {
            throw "Expected 144 games for $season $($entry.Key), got $($entry.Value)."
        }
    }
}

$parent = Split-Path -Parent $OutputPath
if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
$games | Export-Csv -Path $OutputPath -NoTypeInformation -Encoding UTF8
Write-Output "COMPLETE games=$($games.Count) seasons=$($Seasons -join ',') output=$OutputPath"
