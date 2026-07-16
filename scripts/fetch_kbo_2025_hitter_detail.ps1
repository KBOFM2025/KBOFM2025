param(
    [string]$HitterPath = "data/source/kbo_2025_first_team_hitting.csv",
    [string]$SituationOutputPath = "data/source/kbo_2025_hitter_situation_splits.csv",
    [int]$BatchSize = 8
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.Net.Http

$seasonField = "ctl00`$ctl00`$ctl00`$cphContents`$cphContents`$cphContents`$ddlSeason`$ddlSeason"
$seriesField = "ctl00`$ctl00`$ctl00`$cphContents`$cphContents`$cphContents`$ddlSeries`$ddlSeries"
$yearField = "ctl00`$ctl00`$ctl00`$cphContents`$cphContents`$cphContents`$ddlYear"
$playerSeriesField = "ctl00`$ctl00`$ctl00`$cphContents`$cphContents`$cphContents`$ddlSeries"
$orderColumnField = "ctl00`$ctl00`$ctl00`$cphContents`$cphContents`$cphContents`$hfOrderByCol"
$orderDirectionField = "ctl00`$ctl00`$ctl00`$cphContents`$cphContents`$cphContents`$hfOrderBy"
$orderEventTarget = "ctl00`$ctl00`$ctl00`$cphContents`$cphContents`$cphContents`$lbtnOrderBy"
$culture = [System.Globalization.CultureInfo]::InvariantCulture
$situationColumns = @("AVG", "AB", "H", "2B", "3B", "HR", "RBI", "BB", "HBP", "SO", "GDP")
$situationCategories = @("runner_state", "ball_count", "inning", "batting_order", "pitcher_type", "out_count")

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

function New-PostContent {
    param(
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
    return [System.Net.Http.FormUrlEncodedContent]::new($pairs)
}

function Invoke-PostBack {
    param(
        [System.Net.Http.HttpClient]$Client,
        [string]$Path,
        [string]$Html,
        [string]$EventTarget,
        [hashtable]$Overrides = @{}
    )
    $content = New-PostContent $Html $EventTarget $Overrides
    try {
        $response = $Client.PostAsync($Path, $content).Result
        $response.EnsureSuccessStatusCode() | Out-Null
        return $response.Content.ReadAsStringAsync().Result
    }
    finally { $content.Dispose() }
}

function Get-TableHtml {
    param([string]$Html, [string]$Summary)
    $escaped = [regex]::Escape($Summary)
    $match = [regex]::Match($Html, '<table\b[^>]*summary="' + $escaped + '"[^>]*>(.*?)</table>', 'Singleline,IgnoreCase')
    if ($match.Success) { return $match.Groups[1].Value }
    return ""
}

function Read-BasicLeaderboardPage {
    param([string]$Html)
    $table = ""
    foreach ($tableMatch in [regex]::Matches($Html, '<table\b[^>]*>(.*?)</table>', 'Singleline,IgnoreCase')) {
        $candidate = $tableMatch.Groups[1].Value
        if ($candidate -match 'playerId=\d+' -and $candidate -match '>SAC<' -and $candidate -match '>SF<') {
            $table = $candidate
            break
        }
    }
    if ([string]::IsNullOrWhiteSpace($table)) { throw "KBO basic leaderboard table was not found." }
    $rows = [System.Collections.Generic.List[object]]::new()
    foreach ($rowMatch in [regex]::Matches($table, '<tr\b[^>]*>(.*?)</tr>', 'Singleline,IgnoreCase')) {
        $rowHtml = $rowMatch.Groups[1].Value
        $cells = @([regex]::Matches($rowHtml, '<td\b[^>]*>(.*?)</td>', 'Singleline,IgnoreCase') | ForEach-Object { ConvertFrom-HtmlCell $_.Groups[1].Value })
        $playerIdMatch = [regex]::Match($rowHtml, 'playerId=(\d+)', 'IgnoreCase')
        if ($cells.Count -ne 16 -or -not $playerIdMatch.Success) { continue }
        $rows.Add([pscustomobject]@{
            kbo_player_id = $playerIdMatch.Groups[1].Value
            player_name = $cells[1]
            record_team = $cells[2]
            AVG = $cells[3]
            G = $cells[4]
            PA = $cells[5]
            AB = $cells[6]
            R = $cells[7]
            H = $cells[8]
            "2B" = $cells[9]
            "3B" = $cells[10]
            HR = $cells[11]
            TB = $cells[12]
            RBI = $cells[13]
            SAC = $cells[14]
            SF = $cells[15]
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

function Read-SituationRows {
    param([string]$Html, [object]$Player, [string]$SourceUrl)
    $output = [System.Collections.Generic.List[object]]::new()
    $tables = [System.Collections.Generic.List[string]]::new()
    foreach ($tableMatch in [regex]::Matches($Html, '<table\b[^>]*>(.*?)</table>', 'Singleline,IgnoreCase')) {
        $candidate = $tableMatch.Groups[1].Value
        $headers = @([regex]::Matches($candidate, '<th\b[^>]*>(.*?)</th>', 'Singleline,IgnoreCase') | ForEach-Object { ConvertFrom-HtmlCell $_.Groups[1].Value })
        if ($headers.Count -eq 12 -and ($headers[1..11] -join ',') -eq ($situationColumns -join ',')) {
            $tables.Add($candidate)
        }
    }
    if ($tables.Count -ne $situationCategories.Count) {
        throw "Expected $($situationCategories.Count) situation tables, got $($tables.Count)."
    }
    for ($tableIndex = 0; $tableIndex -lt $tables.Count; $tableIndex++) {
        $table = $tables[$tableIndex]
        foreach ($rowMatch in [regex]::Matches($table, '<tr\b[^>]*>(.*?)</tr>', 'Singleline,IgnoreCase')) {
            $cells = @([regex]::Matches($rowMatch.Groups[1].Value, '<td\b[^>]*>(.*?)</td>', 'Singleline,IgnoreCase') | ForEach-Object { ConvertFrom-HtmlCell $_.Groups[1].Value })
            if ($cells.Count -ne 12) { continue }
            $record = [ordered]@{
                season = "2025"
                kbo_player_id = $Player.kbo_player_id
                player_uid = $Player.player_uid
                snapshot_team = $Player.snapshot_team
                player_name = $Player.player_name
                position_group = $Player.position_group
                split_category = $situationCategories[$tableIndex]
                split_label = $cells[0]
            }
            for ($index = 0; $index -lt $situationColumns.Count; $index++) {
                $record[$situationColumns[$index]] = $cells[$index + 1]
            }
            $record["source_url"] = $SourceUrl
            $output.Add([pscustomobject]$record)
        }
    }
    return @($output)
}

function Format-Rate {
    param([decimal]$Numerator, [decimal]$Denominator, [string]$Format)
    if ($Denominator -le 0) { return "" }
    return ($Numerator / $Denominator).ToString($Format, $culture)
}

function Test-DecimalText {
    param([string]$Value)
    return $Value -match '^-?\d+(?:\.\d+)?$'
}

function Get-SacSfResult {
    param([object]$Player, [object]$Basic)
    if ($null -ne $Basic) {
        return [pscustomobject]@{
            SAC = $Basic.SAC
            SF = $Basic.SF
            Candidates = $Basic.SF
            Source = "kbo_basic_leaderboard"
            Confidence = "official"
        }
    }
    foreach ($field in @("PA", "AB", "H", "BB", "HBP", "OBP")) {
        if (-not (Test-DecimalText ([string]$Player.$field))) {
            return [pscustomobject]@{ SAC = ""; SF = ""; Candidates = ""; Source = ""; Confidence = "unavailable" }
        }
    }
    $pa = [int]$Player.PA
    $ab = [int]$Player.AB
    $h = [int]$Player.H
    $bb = [int]$Player.BB
    $hbp = [int]$Player.HBP
    $displayedObp = [decimal]::Parse($Player.OBP, $culture)
    $sacrifices = $pa - $ab - $bb - $hbp
    if ($sacrifices -lt 0) {
        return [pscustomobject]@{ SAC = ""; SF = ""; Candidates = ""; Source = "pa_identity_failed"; Confidence = "unavailable" }
    }
    $candidates = [System.Collections.Generic.List[int]]::new()
    for ($sf = 0; $sf -le $sacrifices; $sf++) {
        $denominator = $ab + $bb + $hbp + $sf
        if ($denominator -le 0) { continue }
        $calculated = [decimal]($h + $bb + $hbp) / [decimal]$denominator
        if ([Math]::Abs($calculated - $displayedObp) -le [decimal]0.0005001) { $candidates.Add($sf) }
    }
    if ($candidates.Count -eq 1) {
        return [pscustomobject]@{
            SAC = $sacrifices - $candidates[0]
            SF = $candidates[0]
            Candidates = [string]$candidates[0]
            Source = "derived_from_pa_and_obp"
            Confidence = "unique_rounding_solution"
        }
    }
    return [pscustomobject]@{
        SAC = ""
        SF = ""
        Candidates = ($candidates -join "|")
        Source = "derived_from_pa_and_obp"
        Confidence = if ($candidates.Count -gt 1) { "ambiguous_rounding" } else { "no_rounding_solution" }
    }
}

$hitters = @(Import-Csv -Encoding UTF8 $HitterPath)
if ($hitters.Count -ne 317) { throw "Expected 317 roster hitters, got $($hitters.Count)." }
if (@($hitters.kbo_player_id | Sort-Object -Unique).Count -ne 317) { throw "Hitter KBO player IDs must be unique." }

$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate
$handler.CookieContainer = [System.Net.CookieContainer]::new()
$client = [System.Net.Http.HttpClient]::new($handler)
$client.BaseAddress = [uri]"https://www.koreabaseball.com"
$client.DefaultRequestHeaders.Referrer = [uri]"https://www.koreabaseball.com/Record/Player/HitterBasic/Basic1.aspx"
$client.Timeout = [timespan]::FromSeconds(45)

try {
    $basicPath = "/Record/Player/HitterBasic/Basic1.aspx"
    $basicResponse = $client.GetAsync($basicPath).Result
    $basicResponse.EnsureSuccessStatusCode() | Out-Null
    $basicHtml = $basicResponse.Content.ReadAsStringAsync().Result
    $basicHtml = Invoke-PostBack $client $basicPath $basicHtml $seasonField @{
        $seasonField = "2025"
        $seriesField = "0"
    }
    $basicHtml = Invoke-PostBack $client $basicPath $basicHtml $orderEventTarget @{
        $orderColumnField = "PA_CN"
        $orderDirectionField = "DESC"
    }

    $leaderboard = [System.Collections.Generic.List[object]]::new()
    $seenPages = [System.Collections.Generic.HashSet[string]]::new()
    while ($true) {
        $pageMatch = [regex]::Match($basicHtml, 'id="[^"]*_hfPage"\s+value="(\d+)"', 'IgnoreCase')
        $page = if ($pageMatch.Success) { $pageMatch.Groups[1].Value } else { "1" }
        if (-not $seenPages.Add($page)) { throw "Repeated KBO leaderboard page $page." }
        foreach ($row in @(Read-BasicLeaderboardPage $basicHtml)) { $leaderboard.Add($row) }
        Write-Output "BASIC_PAGE=$page ROWS=$($leaderboard.Count)"
        $nextTarget = Get-NextPagerTarget $basicHtml
        if ([string]::IsNullOrWhiteSpace($nextTarget)) { break }
        $basicHtml = Invoke-PostBack $client $basicPath $basicHtml $nextTarget
    }

    $leaderboardById = @{}
    foreach ($row in $leaderboard) {
        if ($leaderboardById.ContainsKey($row.kbo_player_id)) { throw "Duplicate 2025 basic row: $($row.kbo_player_id)" }
        $leaderboardById[$row.kbo_player_id] = $row
    }

    $augmented = foreach ($player in $hitters) {
        $basic = $leaderboardById[[string]$player.kbo_player_id]
        $sacSf = Get-SacSfResult $player $basic
        $record = [ordered]@{}
        foreach ($property in $player.PSObject.Properties) { $record[$property.Name] = $property.Value }
        $record["SAC"] = $sacSf.SAC
        $record["SF"] = $sacSf.SF
        $record["PA_OTHER"] = if (
            (Test-DecimalText $player.PA) -and (Test-DecimalText $player.AB) -and
            (Test-DecimalText $player.BB) -and (Test-DecimalText $player.HBP) -and
            (Test-DecimalText ([string]$sacSf.SAC)) -and (Test-DecimalText ([string]$sacSf.SF))
        ) {
            [int]$player.PA - [int]$player.AB - [int]$player.BB - [int]$player.HBP - [int]$sacSf.SAC - [int]$sacSf.SF
        } else { "" }
        $record["SAC_SF_CANDIDATES"] = $sacSf.Candidates
        $record["SAC_SF_SOURCE"] = $sacSf.Source
        $record["SAC_SF_CONFIDENCE"] = $sacSf.Confidence
        if ($player.has_record -eq "1") {
            $pa = if (Test-DecimalText $player.PA) { [decimal]::Parse($player.PA, $culture) } else { [decimal]0 }
            $so = if (Test-DecimalText $player.SO) { [decimal]::Parse($player.SO, $culture) } else { [decimal]0 }
            $bb = if (Test-DecimalText $player.BB) { [decimal]::Parse($player.BB, $culture) } else { [decimal]0 }
            $xbh = if ((Test-DecimalText $player."2B") -and (Test-DecimalText $player."3B") -and (Test-DecimalText $player.HR)) {
                [int]$player."2B" + [int]$player."3B" + [int]$player.HR
            } else { "" }
            $record["ISO"] = if ((Test-DecimalText $player.AVG) -and (Test-DecimalText $player.SLG)) {
                ([decimal]::Parse($player.SLG, $culture) - [decimal]::Parse($player.AVG, $culture)).ToString("0.000", $culture)
            } else { "" }
            $record["K_RATE"] = Format-Rate $so $pa "0.0000"
            $record["BB_RATE"] = Format-Rate $bb $pa "0.0000"
            $record["BB_K"] = Format-Rate $bb $so "0.000"
            $record["XBH"] = $xbh
            $record["XBH_RATE"] = if ($xbh -ne "") { Format-Rate ([decimal]$xbh) $pa "0.0000" } else { "" }
            $record["HR_RATE"] = if (Test-DecimalText $player.HR) { Format-Rate ([decimal]$player.HR) $pa "0.0000" } else { "" }
        }
        else {
            foreach ($column in @("ISO", "K_RATE", "BB_RATE", "BB_K", "XBH", "XBH_RATE", "HR_RATE")) { $record[$column] = "" }
        }
        $record["basic_source_url"] = "https://www.koreabaseball.com/Record/Player/HitterBasic/Basic1.aspx"
        [pscustomobject]$record
    }

    $situationRows = [System.Collections.Generic.List[object]]::new()
    $errors = [System.Collections.Generic.List[string]]::new()
    for ($batchStart = 0; $batchStart -lt $hitters.Count; $batchStart += $BatchSize) {
        $batchEnd = [Math]::Min($batchStart + $BatchSize, $hitters.Count)
        $pendingGets = [System.Collections.Generic.List[object]]::new()
        for ($index = $batchStart; $index -lt $batchEnd; $index++) {
            $player = $hitters[$index]
            if ($player.has_record -ne "1") { continue }
            $path = "/Record/Player/HitterDetail/Situation.aspx?playerId=$($player.kbo_player_id)"
            $pendingGets.Add([pscustomobject]@{ Player = $player; Path = $path; Task = $client.GetAsync($path) })
        }
        $pendingPosts = [System.Collections.Generic.List[object]]::new()
        foreach ($request in $pendingGets) {
            try {
                $response = $request.Task.Result
                $response.EnsureSuccessStatusCode() | Out-Null
                $html = $response.Content.ReadAsStringAsync().Result
                $content = New-PostContent $html $yearField @{$yearField = "2025"; $playerSeriesField = "0"}
                $pendingPosts.Add([pscustomobject]@{
                    Player = $request.Player
                    Path = $request.Path
                    Content = $content
                    Task = $client.PostAsync($request.Path, $content)
                })
            }
            catch { $errors.Add("GET $($request.Player.kbo_player_id) $($request.Player.player_name): $($_.Exception.Message)") }
        }
        foreach ($request in $pendingPosts) {
            try {
                $response = $request.Task.Result
                $response.EnsureSuccessStatusCode() | Out-Null
                $html = $response.Content.ReadAsStringAsync().Result
                if ($html -notmatch '<option selected="selected" value="2025">') { throw "2025 was not selected" }
                $sourceUrl = "https://www.koreabaseball.com$($request.Path)"
                foreach ($row in @(Read-SituationRows $html $request.Player $sourceUrl)) { $situationRows.Add($row) }
            }
            catch { $errors.Add("POST $($request.Player.kbo_player_id) $($request.Player.player_name): $($_.Exception.Message)") }
            finally { $request.Content.Dispose() }
        }
        if ($batchEnd % 48 -eq 0 -or $batchEnd -eq $hitters.Count) {
            Write-Output "SITUATION_FETCHED=$batchEnd/$($hitters.Count) ROWS=$($situationRows.Count) ERRORS=$($errors.Count)"
        }
        Start-Sleep -Milliseconds 25
    }
    if ($errors.Count -gt 0) { throw "KBO situation fetch failures: $($errors -join '; ')" }

    $augmented | Export-Csv $HitterPath -NoTypeInformation -Encoding UTF8
    $situationRows | Sort-Object kbo_player_id, split_category, split_label | Export-Csv $SituationOutputPath -NoTypeInformation -Encoding UTF8
}
finally {
    $client.Dispose()
    $handler.Dispose()
}

$withBasic = @($augmented | Where-Object { -not [string]::IsNullOrWhiteSpace($_.SAC) }).Count
$pitcherTypeRows = @($situationRows | Where-Object split_category -eq "pitcher_type").Count
Write-Output "COMPLETE hitters=$($hitters.Count) basic_matched=$withBasic situation_rows=$($situationRows.Count) pitcher_type_rows=$pitcherTypeRows"
