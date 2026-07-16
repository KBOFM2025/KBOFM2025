param(
    [string]$RosterPath = "data/source/kbo_2025_final_roster.csv",
    [string]$HitterOutputPath = "data/source/kbo_2025_first_team_hitting.csv",
    [string]$PitcherOutputPath = "data/source/kbo_2025_first_team_pitching.csv",
    [string]$FuturesHitterOutputPath = "data/source/kbo_2025_futures_hitting.csv",
    [int]$BatchSize = 8
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.Net.Http

$hitterColumns = @(
    "AVG", "G", "PA", "AB", "R", "H", "2B", "3B", "HR", "TB", "RBI",
    "SB", "CS", "BB", "HBP", "SO", "GDP", "SLG", "OBP", "E"
)
$pitcherColumns = @(
    "ERA", "G", "CG", "SHO", "W", "L", "SV", "HLD", "WPCT", "TBF",
    "IP", "H", "HR", "BB", "HBP", "SO", "R", "ER"
)
$culture = [System.Globalization.CultureInfo]::InvariantCulture

function ConvertFrom-HtmlCell {
    param([string]$Value)
    $text = [regex]::Replace($Value, '<[^>]+>', '')
    return [System.Net.WebUtility]::HtmlDecode($text).Trim()
}

function Read-SeasonRows {
    param(
        [string]$Html,
        [string[]]$Columns
    )
    $results = [System.Collections.Generic.List[object]]::new()
    foreach ($rowMatch in [regex]::Matches($Html, '<tr[^>]*>(.*?)</tr>', 'Singleline,IgnoreCase')) {
        $cells = @(
            [regex]::Matches($rowMatch.Groups[1].Value, '<t[dh][^>]*>(.*?)</t[dh]>', 'Singleline,IgnoreCase') |
                ForEach-Object { ConvertFrom-HtmlCell $_.Groups[1].Value }
        )
        if ($cells.Count -ne ($Columns.Count + 2) -or $cells[0] -ne "2025") { continue }
        $record = [ordered]@{ record_team = $cells[1] }
        for ($index = 0; $index -lt $Columns.Count; $index++) {
            $record[$Columns[$index]] = $cells[$index + 2]
        }
        $results.Add([pscustomobject]$record)
    }
    return @($results)
}

function Convert-InningsToOuts {
    param([string]$Innings)
    if ([string]::IsNullOrWhiteSpace($Innings) -or $Innings -eq "-") { return 0 }
    $normalized = $Innings.Trim().Replace("⅓", " 1/3").Replace("⅔", " 2/3")
    $match = [regex]::Match($normalized, '^(\d+)(?:\s+([12])/3)?$')
    if (-not $match.Success) {
        $fractionOnly = [regex]::Match($normalized, '^([12])/3$')
        if ($fractionOnly.Success) { return [int]$fractionOnly.Groups[1].Value }
        throw "Unrecognized innings value: $Innings"
    }
    $outs = [int]$match.Groups[1].Value * 3
    if ($match.Groups[2].Success) { $outs += [int]$match.Groups[2].Value }
    return $outs
}

function New-BaseRecord {
    param([object]$Player, [string]$SourceUrl, [int]$HasRecord, [string]$RecordTeam)
    return [ordered]@{
        season = "2025"
        kbo_player_id = $Player.kbo_player_id
        player_uid = $Player.player_uid
        snapshot_team = $Player.team
        player_name = $Player.name
        position_group = $Player.position_group
        record_team = $RecordTeam
        has_record = $HasRecord
        source_url = $SourceUrl
    }
}

function Fetch-StatSet {
    param(
        [System.Net.Http.HttpClient]$Client,
        [object[]]$Players,
        [string]$PathTemplate,
        [string[]]$Columns,
        [ValidateSet("hitter", "pitcher")][string]$RecordType
    )
    $output = [System.Collections.Generic.List[object]]::new()
    $errors = [System.Collections.Generic.List[string]]::new()

    for ($batchStart = 0; $batchStart -lt $Players.Count; $batchStart += $BatchSize) {
        $pending = [System.Collections.Generic.List[object]]::new()
        $batchEnd = [Math]::Min($batchStart + $BatchSize, $Players.Count)
        for ($index = $batchStart; $index -lt $batchEnd; $index++) {
            $player = $Players[$index]
            $path = $PathTemplate.Replace("{id}", $player.kbo_player_id)
            $pending.Add([pscustomobject]@{
                Player = $player
                Path = $path
                Task = $Client.GetAsync($path)
            })
        }

        foreach ($request in $pending) {
            try {
                $response = $request.Task.Result
                $response.EnsureSuccessStatusCode() | Out-Null
                $html = $response.Content.ReadAsStringAsync().Result
                $seasonRows = @(Read-SeasonRows $html $Columns)
                $sourceUrl = "https://www.koreabaseball.com$($request.Path)"

                if ($seasonRows.Count -eq 0) {
                    $record = New-BaseRecord $request.Player $sourceUrl 0 ""
                    foreach ($column in $Columns) { $record[$column] = "" }
                    if ($RecordType -eq "hitter") { $record["OPS"] = "" }
                    else {
                        $record["IP_OUTS"] = ""
                        $record["IP_DECIMAL"] = ""
                        $record["WHIP"] = ""
                    }
                    $output.Add([pscustomobject]$record)
                    continue
                }

                foreach ($seasonRow in $seasonRows) {
                    $record = New-BaseRecord $request.Player $sourceUrl 1 $seasonRow.record_team
                    foreach ($column in $Columns) { $record[$column] = $seasonRow.$column }
                    if ($RecordType -eq "hitter") {
                        if ($seasonRow.SLG -match '^\d+(?:\.\d+)?$' -and $seasonRow.OBP -match '^\d+(?:\.\d+)?$') {
                            $ops = [decimal]::Parse($seasonRow.SLG, $culture) + [decimal]::Parse($seasonRow.OBP, $culture)
                            $record["OPS"] = $ops.ToString("0.000", $culture)
                        }
                        else { $record["OPS"] = "" }
                    }
                    else {
                        $outs = Convert-InningsToOuts $seasonRow.IP
                        $record["IP_OUTS"] = $outs
                        $record["IP_DECIMAL"] = if ($outs -gt 0) { ($outs / 3.0).ToString("0.000", $culture) } else { "0.000" }
                        $record["WHIP"] = if ($outs -gt 0) {
                            (([decimal]([int]$seasonRow.H + [int]$seasonRow.BB) * 3) / $outs).ToString("0.00", $culture)
                        } else { "" }
                    }
                    $output.Add([pscustomobject]$record)
                }
            }
            catch {
                $errors.Add("$($request.Player.kbo_player_id) $($request.Player.name): $($_.Exception.Message)")
            }
        }

        if ($batchEnd % 48 -eq 0 -or $batchEnd -eq $Players.Count) {
            Write-Host "TYPE=$RecordType FETCHED=$batchEnd/$($Players.Count) ROWS=$($output.Count) ERRORS=$($errors.Count)"
        }
        Start-Sleep -Milliseconds 20
    }
    if ($errors.Count -gt 0) { throw "KBO stat fetch failures: $($errors -join '; ')" }
    return @($output)
}

$roster = @(Import-Csv -Encoding UTF8 $RosterPath)
if ($roster.Count -ne 636) { throw "Expected 636 final roster players, got $($roster.Count)." }
$hitters = @($roster | Where-Object position_group -ne "P" | Sort-Object kbo_player_id)
$pitchers = @($roster | Where-Object position_group -eq "P" | Sort-Object kbo_player_id)

$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate
$client = [System.Net.Http.HttpClient]::new($handler)
$client.BaseAddress = [uri]"https://www.koreabaseball.com"
$client.DefaultRequestHeaders.Referrer = [uri]"https://www.koreabaseball.com/Record/Player/HitterBasic/Basic1.aspx"
$client.Timeout = [timespan]::FromSeconds(30)

try {
    $firstTeamHitting = @(Fetch-StatSet $client $hitters "/Record/Player/HitterDetail/Total.aspx?playerId={id}" $hitterColumns "hitter")
    $firstTeamPitching = @(Fetch-StatSet $client $pitchers "/Record/Player/PitcherDetail/Total.aspx?playerId={id}" $pitcherColumns "pitcher")
    $futuresHitting = @(Fetch-StatSet $client $hitters "/Futures/Player/HitterTotal.aspx?playerId={id}" $hitterColumns "hitter")
}
finally {
    $client.Dispose()
    $handler.Dispose()
}

$firstTeamHitting | Export-Csv $HitterOutputPath -NoTypeInformation -Encoding UTF8
$firstTeamPitching | Export-Csv $PitcherOutputPath -NoTypeInformation -Encoding UTF8
$futuresHitting | Export-Csv $FuturesHitterOutputPath -NoTypeInformation -Encoding UTF8

Write-Output "COMPLETE hitters=$($hitters.Count)/$($firstTeamHitting.Count) pitchers=$($pitchers.Count)/$($firstTeamPitching.Count) futures_hitters=$($hitters.Count)/$($futuresHitting.Count)"
