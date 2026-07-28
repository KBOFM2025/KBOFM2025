param(
    [string]$RosterPath = "data/source/kbo_2025_final_roster.csv",
    [string]$OutputPath = "data/source/kbo_2025_defense.csv"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.Net.Http

$seasonField = "ctl00`$ctl00`$ctl00`$cphContents`$cphContents`$cphContents`$ddlSeason`$ddlSeason"
$seriesField = "ctl00`$ctl00`$ctl00`$cphContents`$cphContents`$cphContents`$ddlSeries`$ddlSeries"
$path = "/Record/Player/Defense/Basic.aspx"

function ConvertFrom-HtmlCell([string]$Value) {
    $text = [regex]::Replace($Value, '<[^>]+>', '')
    return [System.Net.WebUtility]::HtmlDecode($text).Trim()
}

function Get-FormFields([string]$Html) {
    $fields = [ordered]@{}
    foreach ($match in [regex]::Matches($Html, '<input\b[^>]*>', 'IgnoreCase')) {
        $tag = $match.Value
        $name = [regex]::Match($tag, '\bname="([^"]+)"', 'IgnoreCase')
        if (-not $name.Success) { continue }
        $type = [regex]::Match($tag, '\btype="([^"]+)"', 'IgnoreCase')
        if ($type.Success -and $type.Groups[1].Value -notin @('hidden', 'submit')) { continue }
        $value = [regex]::Match($tag, '\bvalue="([^"]*)"', 'IgnoreCase')
        $fields[[System.Net.WebUtility]::HtmlDecode($name.Groups[1].Value)] = if ($value.Success) {
            [System.Net.WebUtility]::HtmlDecode($value.Groups[1].Value)
        } else { '' }
    }
    foreach ($match in [regex]::Matches($Html, '<select\b[^>]*name="([^"]+)"[^>]*>(.*?)</select>', 'Singleline,IgnoreCase')) {
        $name = [System.Net.WebUtility]::HtmlDecode($match.Groups[1].Value)
        $selected = [regex]::Match($match.Groups[2].Value, '<option\b[^>]*selected(?:="selected")?[^>]*value="([^"]*)"', 'Singleline,IgnoreCase')
        if (-not $selected.Success) { $selected = [regex]::Match($match.Groups[2].Value, '<option\b[^>]*value="([^"]*)"', 'Singleline,IgnoreCase') }
        if ($selected.Success) { $fields[$name] = [System.Net.WebUtility]::HtmlDecode($selected.Groups[1].Value) }
    }
    return $fields
}

function Invoke-PostBack($Client, [string]$Html, [string]$EventTarget, [hashtable]$Overrides = @{}) {
    $fields = Get-FormFields $Html
    $fields['__EVENTTARGET'] = $EventTarget
    $fields['__EVENTARGUMENT'] = ''
    foreach ($entry in $Overrides.GetEnumerator()) { $fields[$entry.Key] = [string]$entry.Value }
    $pairs = [System.Collections.Generic.List[System.Collections.Generic.KeyValuePair[string,string]]]::new()
    foreach ($entry in $fields.GetEnumerator()) {
        $pairs.Add([System.Collections.Generic.KeyValuePair[string,string]]::new([string]$entry.Key, [string]$entry.Value))
    }
    $content = [System.Net.Http.FormUrlEncodedContent]::new($pairs)
    try {
        $response = $Client.PostAsync($path, $content).Result
        $response.EnsureSuccessStatusCode() | Out-Null
        return $response.Content.ReadAsStringAsync().Result
    } finally { $content.Dispose() }
}

function Get-NextTarget([string]$Html) {
    $pageMatch = [regex]::Match($Html, 'id="[^"]*_hfPage"\s+value="(\d+)"', 'IgnoreCase')
    if (-not $pageMatch.Success) { return '' }
    $nextPage = [int]$pageMatch.Groups[1].Value + 1
    foreach ($anchor in [regex]::Matches($Html, '<a\b[^>]*href="([^"]*__doPostBack[^"]*)"[^>]*>(.*?)</a>', 'Singleline,IgnoreCase')) {
        if ((ConvertFrom-HtmlCell $anchor.Groups[2].Value) -ne [string]$nextPage) { continue }
        $target = [regex]::Match([System.Net.WebUtility]::HtmlDecode($anchor.Groups[1].Value), "__doPostBack\('([^']+)'", 'IgnoreCase')
        if ($target.Success) { return $target.Groups[1].Value }
    }
    foreach ($anchor in [regex]::Matches($Html, '<a\b[^>]*id="[^"]*btnNext[^"]*"[^>]*href="([^"]*__doPostBack[^"]*)"', 'Singleline,IgnoreCase')) {
        $target = [regex]::Match([System.Net.WebUtility]::HtmlDecode($anchor.Groups[1].Value), "__doPostBack\('([^']+)'", 'IgnoreCase')
        if ($target.Success) { return $target.Groups[1].Value }
    }
    return ''
}

function Read-DefenseRows([string]$Html, [hashtable]$RosterById) {
    $output = [System.Collections.Generic.List[object]]::new()
    foreach ($table in [regex]::Matches($Html, '<table\b[^>]*>(.*?)</table>', 'Singleline,IgnoreCase')) {
        $candidate = $table.Groups[1].Value
        if ($candidate -notmatch '>FPCT<' -or $candidate -notmatch '>CS%<') { continue }
        foreach ($row in [regex]::Matches($candidate, '<tr\b[^>]*>(.*?)</tr>', 'Singleline,IgnoreCase')) {
            $htmlRow = $row.Groups[1].Value
            $idMatch = [regex]::Match($htmlRow, 'playerId=(\d+)', 'IgnoreCase')
            $cells = @([regex]::Matches($htmlRow, '<td\b[^>]*>(.*?)</td>', 'Singleline,IgnoreCase') | ForEach-Object { ConvertFrom-HtmlCell $_.Groups[1].Value })
            if (-not $idMatch.Success -or $cells.Count -ne 17) { continue }
            $id = $idMatch.Groups[1].Value
            if (-not $RosterById.ContainsKey($id)) { continue }
            $roster = $RosterById[$id]
            $output.Add([pscustomobject][ordered]@{
                season='2025'; kbo_player_id=$id; player_uid=$roster.player_uid
                snapshot_team=$roster.team; player_name=$roster.name; position_group=$roster.position_group
                record_team=$cells[2]; defense_position=$cells[3]; G=$cells[4]; GS=$cells[5]
                IP=$cells[6]; E=$cells[7]; PKO=$cells[8]; PO=$cells[9]; A=$cells[10]
                DP=$cells[11]; FPCT=$cells[12]; PB=$cells[13]; SB=$cells[14]
                CS=$cells[15]; CS_PCT=$cells[16]
                source_url='https://www.koreabaseball.com/Record/Player/Defense/Basic.aspx'
            })
        }
        break
    }
    return @($output)
}

$rosterRows = @(Import-Csv -Encoding UTF8 $RosterPath | Where-Object position_group -ne 'P')
$rosterById = @{}
foreach ($row in $rosterRows) { $rosterById[[string]$row.kbo_player_id] = $row }

$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate
$client = [System.Net.Http.HttpClient]::new($handler)
$client.BaseAddress = [uri]'https://www.koreabaseball.com'
$client.Timeout = [timespan]::FromSeconds(45)
try {
    $response = $client.GetAsync($path).Result
    $response.EnsureSuccessStatusCode() | Out-Null
    $html = $response.Content.ReadAsStringAsync().Result
    $html = Invoke-PostBack $client $html $seasonField @{$seasonField='2025'; $seriesField='0'}
    if ($html -notmatch '<option selected="selected" value="2025">') { throw '2025 season selection failed.' }
    $rows = [System.Collections.Generic.List[object]]::new()
    $seen = [System.Collections.Generic.HashSet[string]]::new()
    $seenPages = [System.Collections.Generic.HashSet[string]]::new()
    while ($true) {
        $pageMatch = [regex]::Match($html, 'id="[^"]*_hfPage"\s+value="(\d+)"', 'IgnoreCase')
        $page = if ($pageMatch.Success) { $pageMatch.Groups[1].Value } else { '1' }
        if (-not $seenPages.Add($page)) { throw "Repeated defense page $page" }
        foreach ($row in @(Read-DefenseRows $html $rosterById)) {
            $key = "$($row.kbo_player_id):$($row.defense_position)"
            if ($seen.Add($key)) { $rows.Add($row) }
        }
        $next = Get-NextTarget $html
        if ([string]::IsNullOrWhiteSpace($next)) { break }
        $html = Invoke-PostBack $client $html $next
    }
    # 최종 보유선수 317명 중 2025 KBO 1군 수비 출전 기록이 있는 선수만 남긴다.
    if ($rows.Count -lt 90) { throw "Too few matched 2025 defense rows: $($rows.Count)" }
    $rows | Sort-Object snapshot_team, player_name, defense_position | Export-Csv $OutputPath -NoTypeInformation -Encoding UTF8
    $players = @($rows.kbo_player_id | Sort-Object -Unique).Count
    Write-Output "COMPLETE rows=$($rows.Count) players=$players output=$OutputPath"
} finally {
    $client.Dispose(); $handler.Dispose()
}
