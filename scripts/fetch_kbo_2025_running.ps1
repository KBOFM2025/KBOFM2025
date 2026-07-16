param(
    [string]$HitterPath = "data/source/kbo_2025_first_team_hitting.csv",
    [string]$OutputPath = "data/source/kbo_2025_running.csv"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.Net.Http

$seasonField = "ctl00`$ctl00`$ctl00`$cphContents`$cphContents`$cphContents`$ddlSeason`$ddlSeason"
$seriesField = "ctl00`$ctl00`$ctl00`$cphContents`$cphContents`$cphContents`$ddlSeries`$ddlSeries"
$orderColumnField = "ctl00`$ctl00`$ctl00`$cphContents`$cphContents`$cphContents`$hfOrderByCol"
$orderDirectionField = "ctl00`$ctl00`$ctl00`$cphContents`$cphContents`$cphContents`$hfOrderBy"
$orderEventTarget = "ctl00`$ctl00`$ctl00`$cphContents`$cphContents`$cphContents`$lbtnOrderBy"
$sourceUrl = "https://www.koreabaseball.com/Record/Player/Runner/Basic.aspx"

function ConvertFrom-HtmlCell {
    param([string]$Value)
    $text = [regex]::Replace($Value, '<[^>]+>', '')
    return [System.Net.WebUtility]::HtmlDecode($text).Trim()
}

function Get-FormFields {
    param([string]$Html)
    $fields = [ordered]@{}
    foreach ($inputMatch in [regex]::Matches($Html, '<input\b[^>]*>', 'IgnoreCase')) {
        $tag = $inputMatch.Value
        $nameMatch = [regex]::Match($tag, '\bname="([^"]+)"', 'IgnoreCase')
        if (-not $nameMatch.Success) { continue }
        $typeMatch = [regex]::Match($tag, '\btype="([^"]+)"', 'IgnoreCase')
        if ($typeMatch.Success -and $typeMatch.Groups[1].Value -notin @("hidden", "submit")) { continue }
        $valueMatch = [regex]::Match($tag, '\bvalue="([^"]*)"', 'IgnoreCase')
        $fields[[System.Net.WebUtility]::HtmlDecode($nameMatch.Groups[1].Value)] = if ($valueMatch.Success) {
            [System.Net.WebUtility]::HtmlDecode($valueMatch.Groups[1].Value)
        } else { "" }
    }
    foreach ($selectMatch in [regex]::Matches($Html, '<select\b[^>]*name="([^"]+)"[^>]*>(.*?)</select>', 'Singleline,IgnoreCase')) {
        $name = [System.Net.WebUtility]::HtmlDecode($selectMatch.Groups[1].Value)
        $selected = [regex]::Match($selectMatch.Groups[2].Value, '<option\b[^>]*selected(?:="selected")?[^>]*value="([^"]*)"', 'Singleline,IgnoreCase')
        if (-not $selected.Success) {
            $selected = [regex]::Match($selectMatch.Groups[2].Value, '<option\b[^>]*value="([^"]*)"', 'Singleline,IgnoreCase')
        }
        if ($selected.Success) { $fields[$name] = [System.Net.WebUtility]::HtmlDecode($selected.Groups[1].Value) }
    }
    return $fields
}

function Invoke-PostBack {
    param(
        [System.Net.Http.HttpClient]$Client,
        [string]$Path,
        [string]$Html,
        [string]$EventTarget,
        [hashtable]$Overrides = @{}
    )
    $fields = Get-FormFields $Html
    $fields["__EVENTTARGET"] = $EventTarget
    $fields["__EVENTARGUMENT"] = ""
    foreach ($entry in $Overrides.GetEnumerator()) { $fields[$entry.Key] = [string]$entry.Value }
    $pairs = [System.Collections.Generic.List[System.Collections.Generic.KeyValuePair[string,string]]]::new()
    foreach ($entry in $fields.GetEnumerator()) {
        $pairs.Add([System.Collections.Generic.KeyValuePair[string,string]]::new([string]$entry.Key, [string]$entry.Value))
    }
    $content = [System.Net.Http.FormUrlEncodedContent]::new($pairs)
    try {
        $response = $Client.PostAsync($Path, $content).Result
        $response.EnsureSuccessStatusCode() | Out-Null
        return $response.Content.ReadAsStringAsync().Result
    }
    finally { $content.Dispose() }
}

function Read-RunnerPage {
    param([string]$Html)
    $table = ""
    foreach ($tableMatch in [regex]::Matches($Html, '<table\b[^>]*>(.*?)</table>', 'Singleline,IgnoreCase')) {
        $candidate = $tableMatch.Groups[1].Value
        if ($candidate -match 'playerId=\d+' -and $candidate -match '>SBA<' -and $candidate -match '>OOB<' -and $candidate -match '>PKO<') {
            $table = $candidate
            break
        }
    }
    if ([string]::IsNullOrWhiteSpace($table)) { throw "KBO runner table was not found." }

    $rows = [System.Collections.Generic.List[object]]::new()
    foreach ($rowMatch in [regex]::Matches($table, '<tr\b[^>]*>(.*?)</tr>', 'Singleline,IgnoreCase')) {
        $rowHtml = $rowMatch.Groups[1].Value
        $cells = @([regex]::Matches($rowHtml, '<td\b[^>]*>(.*?)</td>', 'Singleline,IgnoreCase') | ForEach-Object { ConvertFrom-HtmlCell $_.Groups[1].Value })
        $playerIdMatch = [regex]::Match($rowHtml, 'playerId=(\d+)', 'IgnoreCase')
        if ($cells.Count -ne 10 -or -not $playerIdMatch.Success) { continue }
        $rows.Add([pscustomobject]@{
            kbo_player_id = $playerIdMatch.Groups[1].Value
            player_name = $cells[1]
            record_team = $cells[2]
            G = $cells[3]
            SBA = $cells[4]
            SB = $cells[5]
            CS = $cells[6]
            "SB_PCT" = $cells[7]
            OOB = $cells[8]
            PKO = $cells[9]
        })
    }
    return @($rows)
}

function Get-NextPagerTarget {
    param([string]$Html)
    $pageMatch = [regex]::Match($Html, 'id="[^"]*_hfPage"\s+value="(\d+)"', 'IgnoreCase')
    if (-not $pageMatch.Success) { return "" }
    $currentPage = [int]$pageMatch.Groups[1].Value
    foreach ($anchorMatch in [regex]::Matches($Html, '<a\b[^>]*href="([^"]*__doPostBack[^"]*)"[^>]*>(.*?)</a>', 'Singleline,IgnoreCase')) {
        $href = [System.Net.WebUtility]::HtmlDecode($anchorMatch.Groups[1].Value)
        $targetMatch = [regex]::Match($href, "__doPostBack\('([^']+)','[^']*'\)")
        if (-not $targetMatch.Success) { continue }
        $text = ConvertFrom-HtmlCell $anchorMatch.Groups[2].Value
        if ($text -eq [string]($currentPage + 1)) { return $targetMatch.Groups[1].Value }
    }
    foreach ($anchorMatch in [regex]::Matches($Html, '<a\b[^>]*id="([^"]*btnNext[^"]*)"[^>]*href="([^"]*__doPostBack[^"]*)"', 'Singleline,IgnoreCase')) {
        $href = [System.Net.WebUtility]::HtmlDecode($anchorMatch.Groups[2].Value)
        $targetMatch = [regex]::Match($href, "__doPostBack\('([^']+)','[^']*'\)")
        if ($targetMatch.Success) { return $targetMatch.Groups[1].Value }
    }
    return ""
}

$hitters = @(Import-Csv -Encoding UTF8 $HitterPath)
if ($hitters.Count -ne 317) { throw "Expected 317 roster hitters, got $($hitters.Count)." }
if (@($hitters.kbo_player_id | Sort-Object -Unique).Count -ne 317) { throw "Hitter KBO player IDs must be unique." }

$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate
$handler.CookieContainer = [System.Net.CookieContainer]::new()
$client = [System.Net.Http.HttpClient]::new($handler)
$client.BaseAddress = [uri]"https://www.koreabaseball.com"
$client.DefaultRequestHeaders.Referrer = [uri]$sourceUrl
$client.Timeout = [timespan]::FromSeconds(45)

try {
    $path = "/Record/Player/Runner/Basic.aspx"
    $response = $client.GetAsync($path).Result
    $response.EnsureSuccessStatusCode() | Out-Null
    $html = $response.Content.ReadAsStringAsync().Result
    $html = Invoke-PostBack $client $path $html $seasonField @{
        $seasonField = "2025"
        $seriesField = "0"
    }
    $html = Invoke-PostBack $client $path $html $orderEventTarget @{
        $orderColumnField = "GAME_CN"
        $orderDirectionField = "DESC"
    }

    $leagueRows = [System.Collections.Generic.List[object]]::new()
    $seenPages = [System.Collections.Generic.HashSet[string]]::new()
    while ($true) {
        $pageMatch = [regex]::Match($html, 'id="[^"]*_hfPage"\s+value="(\d+)"', 'IgnoreCase')
        $page = if ($pageMatch.Success) { $pageMatch.Groups[1].Value } else { "1" }
        if (-not $seenPages.Add($page)) { throw "Repeated KBO runner page $page." }
        foreach ($row in @(Read-RunnerPage $html)) { $leagueRows.Add($row) }
        Write-Output "RUNNER_PAGE=$page ROWS=$($leagueRows.Count)"
        $nextTarget = Get-NextPagerTarget $html
        if ([string]::IsNullOrWhiteSpace($nextTarget)) { break }
        $html = Invoke-PostBack $client $path $html $nextTarget
    }
}
finally {
    $client.Dispose()
    $handler.Dispose()
}

$leagueById = @{}
foreach ($row in $leagueRows) {
    if ($leagueById.ContainsKey($row.kbo_player_id)) { throw "Duplicate runner row: $($row.kbo_player_id)" }
    if ([int]$row.SBA -ne ([int]$row.SB + [int]$row.CS)) { throw "SBA identity failed: $($row.kbo_player_id)" }
    $leagueById[$row.kbo_player_id] = $row
}

$output = foreach ($player in $hitters) {
    $running = $leagueById[[string]$player.kbo_player_id]
    [pscustomobject][ordered]@{
        season = "2025"
        kbo_player_id = $player.kbo_player_id
        player_uid = $player.player_uid
        snapshot_team = $player.snapshot_team
        player_name = $player.player_name
        position_group = $player.position_group
        record_team = if ($null -ne $running) { $running.record_team } else { "" }
        has_record = if ($null -ne $running) { 1 } else { 0 }
        G = if ($null -ne $running) { $running.G } else { "" }
        SBA = if ($null -ne $running) { $running.SBA } else { "" }
        SB = if ($null -ne $running) { $running.SB } else { "" }
        CS = if ($null -ne $running) { $running.CS } else { "" }
        SB_PCT = if ($null -ne $running) { $running.SB_PCT } else { "" }
        OOB = if ($null -ne $running) { $running.OOB } else { "" }
        PKO = if ($null -ne $running) { $running.PKO } else { "" }
        source_url = $sourceUrl
    }
}

$hitterById = @{}
foreach ($player in $hitters) { $hitterById[$player.kbo_player_id] = $player }
$mismatches = [System.Collections.Generic.List[string]]::new()
foreach ($row in $output) {
    if ($row.has_record -ne 1) { continue }
    $hitting = $hitterById[$row.kbo_player_id]
    if ($null -eq $hitting) { $mismatches.Add("missing hitter $($row.kbo_player_id)"); continue }
    if ($hitting.SB -ne $row.SB -or $hitting.CS -ne $row.CS) {
        $mismatches.Add("$($row.kbo_player_id) hitting=$($hitting.SB)/$($hitting.CS) running=$($row.SB)/$($row.CS)")
    }
}
if ($mismatches.Count -gt 0) { throw "Hitting/running SB-CS mismatches: $($mismatches -join '; ')" }

$output | Export-Csv $OutputPath -NoTypeInformation -Encoding UTF8
$matched = @($output | Where-Object has_record -eq 1).Count
Write-Output "COMPLETE league_rows=$($leagueRows.Count) roster_hitters=$($hitters.Count) matched=$matched no_record=$($hitters.Count - $matched)"
