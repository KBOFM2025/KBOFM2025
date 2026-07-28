param(
    [string]$RosterPath = "data/source/kbo_2025_final_roster.csv",
    [string]$OutputPath = "data/source/kbo_player_career_history.csv",
    [int]$BatchSize = 10
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.Net.Http

function ConvertFrom-HtmlCell {
    param([string]$Value)
    $text = [regex]::Replace($Value, '<[^>]+>', '')
    return [System.Net.WebUtility]::HtmlDecode($text).Trim()
}

function Read-CareerRows {
    param([string]$Html, [object]$Player, [string]$SourceUrl)
    $seen = @{}
    $result = [System.Collections.Generic.List[object]]::new()
    foreach ($rowMatch in [regex]::Matches($Html, '<tr[^>]*>(.*?)</tr>', 'Singleline,IgnoreCase')) {
        $cells = @(
            [regex]::Matches($rowMatch.Groups[1].Value, '<t[dh][^>]*>(.*?)</t[dh]>', 'Singleline,IgnoreCase') |
                ForEach-Object { ConvertFrom-HtmlCell $_.Groups[1].Value }
        )
        if ($cells.Count -lt 3 -or $cells[0] -notmatch '^\d{4}$' -or [int]$cells[0] -gt 2025 -or [string]::IsNullOrWhiteSpace($cells[1])) { continue }
        $key = "$($cells[0])|$($cells[1])"
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        $result.Add([pscustomobject]@{
            kbo_player_id = $Player.kbo_player_id
            player_name = $Player.name
            season = [int]$cells[0]
            record_team = $cells[1]
            league = "KBO"
            source_url = $SourceUrl
        })
    }
    return @($result)
}

$roster = @(Import-Csv -Encoding UTF8 $RosterPath)
if ($roster.Count -ne 636) { throw "Expected 636 roster players, got $($roster.Count)." }

$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate
$client = [System.Net.Http.HttpClient]::new($handler)
$client.BaseAddress = [uri]"https://www.koreabaseball.com"
$client.DefaultRequestHeaders.Referrer = [uri]"https://www.koreabaseball.com/Player/Search.aspx"
$client.Timeout = [timespan]::FromSeconds(30)
$history = [System.Collections.Generic.List[object]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    for ($start = 0; $start -lt $roster.Count; $start += $BatchSize) {
        $pending = [System.Collections.Generic.List[object]]::new()
        $end = [Math]::Min($start + $BatchSize, $roster.Count)
        for ($index = $start; $index -lt $end; $index++) {
            $player = $roster[$index]
            $type = if ($player.position_group -eq "P") { "Pitcher" } else { "Hitter" }
            $path = "/Record/Player/$($type)Detail/Total.aspx?playerId=$($player.kbo_player_id)"
            $pending.Add([pscustomobject]@{ Player = $player; Path = $path; Task = $client.GetAsync($path) })
        }
        foreach ($request in $pending) {
            try {
                $response = $request.Task.Result
                $response.EnsureSuccessStatusCode() | Out-Null
                $html = $response.Content.ReadAsStringAsync().Result
                $sourceUrl = "https://www.koreabaseball.com$($request.Path)"
                foreach ($row in @(Read-CareerRows $html $request.Player $sourceUrl)) { $history.Add($row) }
            }
            catch { $errors.Add("$($request.Player.kbo_player_id) $($request.Player.name): $($_.Exception.Message)") }
        }
        if ($end % 100 -eq 0 -or $end -eq $roster.Count) {
            Write-Output "FETCHED=$end/$($roster.Count) HISTORY=$($history.Count) ERRORS=$($errors.Count)"
        }
    }
}
finally { $client.Dispose(); $handler.Dispose() }

if ($errors.Count -gt 0) { throw "Career history failures: $($errors -join '; ')" }
$history | Sort-Object kbo_player_id, season, record_team | Export-Csv $OutputPath -NoTypeInformation -Encoding UTF8
Write-Output "COMPLETE players=$($roster.Count) history_rows=$($history.Count) output=$OutputPath"
