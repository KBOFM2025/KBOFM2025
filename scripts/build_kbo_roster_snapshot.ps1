param(
    [string]$OpeningRosterPath = "data/source/kbo_2025_opening_roster.csv",
    [string]$MovementJsonPath = "data/source/kbo_html/trades_2025.json",
    [string]$OutputRosterPath = "data/source/kbo_2025_roster_2025-10-31.csv",
    [string]$OutputMovementPath = "data/source/kbo_2025_membership_movements.csv"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$teamNames = @{
    "KIA" = "KIA 타이거즈"
    "삼성" = "삼성 라이온즈"
    "LG" = "LG 트윈스"
    "두산" = "두산 베어스"
    "KT" = "KT 위즈"
    "SSG" = "SSG 랜더스"
    "롯데" = "롯데 자이언츠"
    "한화" = "한화 이글스"
    "NC" = "NC 다이노스"
    "키움" = "키움 히어로즈"
}
$positionCodes = @{ "투수" = "P"; "포수" = "C"; "내야수" = "IF"; "외야수" = "OF" }
$membershipTypes = @(
    "개명", "군보류", "군보류 자유계약선수", "소속선수 추가 등록",
    "웨이버", "임의해지", "임의해지 복귀", "자유계약선수", "트레이드"
)
$removeTypes = @("군보류", "군보류 자유계약선수", "웨이버", "임의해지", "자유계약선수")

function Parse-PlayerLabel {
    param([string]$Label)
    $match = [regex]::Match($Label, "^(.*)\((투수|포수|내야수|외야수)\)$")
    if (-not $match.Success) { return $null }
    return [pscustomobject]@{
        Name = $match.Groups[1].Value.Trim()
        PositionName = $match.Groups[2].Value
        PositionGroup = $positionCodes[$match.Groups[2].Value]
    }
}

function Find-PlayerIndexes {
    param(
        [System.Collections.ArrayList]$Roster,
        [string]$Team,
        [string]$Name,
        [string]$PositionGroup
    )
    $indexes = [System.Collections.Generic.List[int]]::new()
    for ($index = 0; $index -lt $Roster.Count; $index++) {
        $player = $Roster[$index]
        if ($player.team -eq $Team -and $player.name -eq $Name -and $player.position_group -eq $PositionGroup) {
            $indexes.Add($index)
        }
    }
    return @($indexes)
}

$openingRows = @(Import-Csv -Encoding UTF8 $OpeningRosterPath)
if ($openingRows.Count -ne 597) { throw "Opening roster must contain 597 players." }

$roster = [System.Collections.ArrayList]::new()
foreach ($row in $openingRows) {
    [void]$roster.Add([pscustomobject]@{
        snapshot_date = "2025-10-31"
        team = $row.team
        name = $row.name
        position_group = $row.position_group
        position_name = $row.position_name
        is_rookie = [int]$row.is_rookie
        is_foreign = [int]$row.is_foreign
        note = $row.note
        source_uid = "KBO-2025-S$($row.source_sheet)-$($row.source_cell)"
        membership_source = "opening_roster"
        last_movement_date = ""
        last_movement_type = ""
        source = $row.source
    })
}

$movementJson = Get-Content -Raw -Encoding UTF8 $MovementJsonPath | ConvertFrom-Json
$movements = @(
    $movementJson.rows |
        ForEach-Object {
            $cells = @($_.row | ForEach-Object { $_.Text })
            [pscustomobject]@{
                date = [datetime]$cells[0]
                type = $cells[1]
                team_short = $cells[2]
                player_label = $cells[3]
                detail = $cells[4]
            }
        } |
        Where-Object {
            $_.date -ge [datetime]"2025-02-11" -and
            $_.date -le [datetime]"2025-10-31" -and
            $_.type -in $membershipTypes
        } |
        Sort-Object date, type, team_short, player_label
)

$audit = [System.Collections.Generic.List[object]]::new()
$eventNumber = 0
foreach ($movement in $movements) {
    $eventNumber++
    $parsed = Parse-PlayerLabel $movement.player_label
    if ($null -eq $parsed) {
        if ($movement.player_label -like "신인*") {
            continue
        }
        throw "Unrecognized player label: $($movement.player_label)"
    }
    if (-not $teamNames.ContainsKey($movement.team_short)) {
        throw "Unrecognized team: $($movement.team_short)"
    }

    $team = $teamNames[$movement.team_short]
    $action = "ignored"
    $matchCount = 0
    $warning = ""

    if ($movement.type -eq "개명") {
        $oldNameMatch = [regex]::Match($movement.detail, "개명전:(.*)$")
        if (-not $oldNameMatch.Success) { throw "Missing former name: $($movement.detail)" }
        $oldName = $oldNameMatch.Groups[1].Value.Trim()
        $indexes = @(Find-PlayerIndexes $roster $team $oldName $parsed.PositionGroup)
        $matchCount = $indexes.Count
        if ($matchCount -eq 1) {
            $player = $roster[$indexes[0]]
            $player.name = $parsed.Name
            $player.last_movement_date = $movement.date.ToString("yyyy-MM-dd")
            $player.last_movement_type = $movement.type
            $action = "renamed"
        }
        elseif ($matchCount -eq 0) {
            $renamedIndexes = @(Find-PlayerIndexes $roster $team $parsed.Name $parsed.PositionGroup)
            if ($renamedIndexes.Count -eq 1) {
                $action = "already_renamed"
            }
            elseif ($renamedIndexes.Count -eq 0) {
                # 기준 명단에 없던 선수가 뒤의 추가 등록에서 새 이름으로 들어오는 경우.
                $action = "rename_not_on_roster"
            }
            else {
                $warning = "rename target count=$matchCount, renamed target count=$($renamedIndexes.Count)"
            }
        }
        else { $warning = "rename target count=$matchCount" }
    }
    elseif ($movement.type -eq "소속선수 추가 등록" -or $movement.type -eq "임의해지 복귀") {
        $indexes = @(Find-PlayerIndexes $roster $team $parsed.Name $parsed.PositionGroup)
        $matchCount = $indexes.Count
        if ($matchCount -eq 0) {
            [void]$roster.Add([pscustomobject]@{
                snapshot_date = "2025-10-31"
                team = $team
                name = $parsed.Name
                position_group = $parsed.PositionGroup
                position_name = $parsed.PositionName
                is_rookie = 0
                is_foreign = [int]($movement.detail -notmatch "육성선수|군보류" -and $parsed.Name -notin @("이용규", "박준영"))
                note = $movement.detail
                source_uid = "KBO-2025-M$eventNumber"
                membership_source = "movement"
                last_movement_date = $movement.date.ToString("yyyy-MM-dd")
                last_movement_type = $movement.type
                source = "https://www.koreabaseball.com/Player/Trade.aspx"
            })
            $action = "added"
        }
        else {
            $action = "already_present"
            if ($matchCount -gt 1) { $warning = "add target count=$matchCount" }
        }
    }
    elseif ($movement.type -in $removeTypes) {
        $indexes = @(Find-PlayerIndexes $roster $team $parsed.Name $parsed.PositionGroup)
        $matchCount = $indexes.Count
        if ($matchCount -eq 1) {
            $roster.RemoveAt($indexes[0])
            $action = "removed"
        }
        elseif ($matchCount -eq 0) {
            $action = "already_absent"
        }
        else {
            $warning = "ambiguous remove target count=$matchCount"
        }
    }
    elseif ($movement.type -eq "트레이드") {
        $tradeMatch = [regex]::Match($movement.detail, "^(.+)→(.+)$")
        if (-not $tradeMatch.Success) { throw "Unrecognized trade detail: $($movement.detail)" }
        $sourceShort = $tradeMatch.Groups[1].Value.Trim()
        if (-not $teamNames.ContainsKey($sourceShort)) { throw "Unrecognized trade source: $sourceShort" }
        $sourceTeam = $teamNames[$sourceShort]
        $indexes = @(Find-PlayerIndexes $roster $sourceTeam $parsed.Name $parsed.PositionGroup)
        $matchCount = $indexes.Count
        if ($matchCount -eq 1) {
            $player = $roster[$indexes[0]]
            $player.team = $team
            $player.last_movement_date = $movement.date.ToString("yyyy-MM-dd")
            $player.last_movement_type = $movement.type
            $action = "traded"
        }
        else { $warning = "trade source count=$matchCount" }
    }

    $audit.Add([pscustomobject]@{
        date = $movement.date.ToString("yyyy-MM-dd")
        type = $movement.type
        team = $team
        player = $parsed.Name
        position_group = $parsed.PositionGroup
        detail = $movement.detail
        action = $action
        match_count = $matchCount
        warning = $warning
    })
}

$outputDirectory = Split-Path -Parent $OutputRosterPath
if ($outputDirectory) { New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null }
$roster |
    Sort-Object team, position_group, name, source_uid |
    Export-Csv -Path $OutputRosterPath -NoTypeInformation -Encoding UTF8
$audit | Export-Csv -Path $OutputMovementPath -NoTypeInformation -Encoding UTF8

$warnings = @($audit | Where-Object warning)
Write-Output "OPENING=$($openingRows.Count) FINAL=$($roster.Count) EVENTS=$($audit.Count) WARNINGS=$($warnings.Count)"
$roster | Group-Object team | Sort-Object Name | Select-Object Name, Count
$audit | Group-Object action | Sort-Object Name | Select-Object Name, Count
if ($warnings.Count -gt 0) {
    Write-Warning ($warnings | Format-Table -AutoSize | Out-String)
}
