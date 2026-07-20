param(
    [string]$OutputPath = "data/source/kbo_2025_final_first_team.csv"
)

$ErrorActionPreference = "Stop"
$registerUrl = "https://www.koreabaseball.com/Player/RegisterAll.aspx"
$eventTarget = 'ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$btnSearch'
$dateField = 'ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$hfSearchDate'

# 구단별 2025 정규시즌 최종 경기 당일의 공식 1군 등록 현황이다.
$teamDates = [ordered]@{
    "LG 트윈스" = @{ code = "LG"; date = "20251001" }
    "한화 이글스" = @{ code = "한화"; date = "20251003" }
    "SSG 랜더스" = @{ code = "SSG"; date = "20251004" }
    "삼성 라이온즈" = @{ code = "삼성"; date = "20251004" }
    "NC 다이노스" = @{ code = "NC"; date = "20251004" }
    "KT 위즈" = @{ code = "KT"; date = "20251003" }
    "롯데 자이언츠" = @{ code = "롯데"; date = "20250930" }
    "KIA 타이거즈" = @{ code = "KIA"; date = "20251004" }
    "두산 베어스" = @{ code = "두산"; date = "20250930" }
    "키움 히어로즈" = @{ code = "키움"; date = "20250930" }
}

function Get-RegisterPage([string]$rosterDate) {
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $page = Invoke-WebRequest -UseBasicParsing -WebSession $session -Uri $registerUrl
    $form = @{}
    $hiddenPattern = '<input[^>]+type="hidden"[^>]+name="([^"]+)"[^>]+value="([^"]*)"[^>]*>'
    foreach ($match in [regex]::Matches($page.Content, $hiddenPattern)) {
        $name = [System.Net.WebUtility]::HtmlDecode($match.Groups[1].Value)
        $value = [System.Net.WebUtility]::HtmlDecode($match.Groups[2].Value)
        $form[$name] = $value
    }
    $form['__EVENTTARGET'] = $eventTarget
    $form['__EVENTARGUMENT'] = ''
    $form[$dateField] = $rosterDate
    return (Invoke-WebRequest -UseBasicParsing -WebSession $session -Method Post -Uri $registerUrl -Body $form).Content
}

$officialRoster = Import-Csv "data/source/kbo_2025_final_roster.csv"
$officialByName = @{}
foreach ($player in $officialRoster) {
    $officialByName["$($player.team)|$($player.name)"] = $player.kbo_player_id
    if (-not [string]::IsNullOrWhiteSpace($player.profile_name)) {
        $officialByName["$($player.team)|$($player.profile_name)"] = $player.kbo_player_id
    }
}

$pages = @{}
$rows = New-Object System.Collections.Generic.List[object]
$positionGroups = @("P", "C", "IF", "OF")
foreach ($teamName in $teamDates.Keys) {
    $entry = $teamDates[$teamName]
    if (-not $pages.ContainsKey($entry.date)) {
        $pages[$entry.date] = Get-RegisterPage $entry.date
    }
    $html = $pages[$entry.date]
    $teamPattern = '<th scope="row" class="fir">\s*' + [regex]::Escape($entry.code) + '<br/><br/>\d+명</th>(?<cells>.*?)</tr>'
    $teamMatch = [regex]::Match($html, $teamPattern, [System.Text.RegularExpressions.RegexOptions]::Singleline)
    if (-not $teamMatch.Success) {
        throw "$teamName ($($entry.date)) 등록 명단을 찾지 못했습니다."
    }
    $cells = [regex]::Matches($teamMatch.Groups['cells'].Value, '<td[^>]*>(?<body>.*?)</td>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
    if ($cells.Count -lt 6) {
        throw "$teamName 등록 명단의 포지션 열이 올바르지 않습니다."
    }
    for ($cellIndex = 2; $cellIndex -le 5; $cellIndex++) {
        $positionGroup = $positionGroups[$cellIndex - 2]
        $playerMatches = [regex]::Matches($cells[$cellIndex].Groups['body'].Value, '<li>\s*(?<name>[^<(]+?)\s*\((?<number>[^)]*)\)\s*</li>')
        foreach ($playerMatch in $playerMatches) {
            $playerName = [System.Net.WebUtility]::HtmlDecode($playerMatch.Groups['name'].Value.Trim())
            $key = "$teamName|$playerName"
            $rows.Add([pscustomobject]@{
                snapshot_date = "2025-10-31"
                team = $teamName
                roster_date = "$($entry.date.Substring(0,4))-$($entry.date.Substring(4,2))-$($entry.date.Substring(6,2))"
                kbo_player_id = $officialByName[$key]
                name = $playerName
                position_group = $positionGroup
                uniform_number = $playerMatch.Groups['number'].Value.Trim()
                source_url = $registerUrl
            })
        }
    }
}

$unmatched = @($rows | Where-Object { [string]::IsNullOrWhiteSpace($_.kbo_player_id) })
if ($unmatched.Count) {
    $names = ($unmatched | ForEach-Object { "$($_.team) $($_.name)" }) -join ", "
    throw "KBO 선수 ID를 찾지 못한 등록 선수가 있습니다: $names"
}
$rows | Sort-Object team, position_group, name | Export-Csv -NoTypeInformation -Encoding utf8 $OutputPath
$rows | Group-Object team | Sort-Object Name | ForEach-Object { "$($_.Name): $($_.Count)명" }
