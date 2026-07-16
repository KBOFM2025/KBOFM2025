param(
    [string]$RosterPath = "data/source/kbo_2025_roster_2025-10-31.csv",
    [string]$CandidatePath = "data/source/kbo_2025_profile_candidates.csv",
    [string]$MatchedPath = "data/source/kbo_2025_profile_matches.csv",
    [string]$ReviewPath = "data/source/kbo_2025_profile_match_review.csv"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$teamNames = @{
    "KIA" = "KIA 타이거즈"; "삼성" = "삼성 라이온즈"; "LG" = "LG 트윈스"
    "두산" = "두산 베어스"; "KT" = "KT 위즈"; "SSG" = "SSG 랜더스"
    "롯데" = "롯데 자이언츠"; "한화" = "한화 이글스"; "NC" = "NC 다이노스"
    "키움" = "키움 히어로즈"
}
$positionNames = @{ "P" = "투수"; "C" = "포수"; "IF" = "내야수"; "OF" = "외야수" }

# 동명이인, 등록 명단 오타, 기준일 이후 개명 때문에 자동 검색으로 확정할 수 없는 선수.
# 키는 "기준일 소속|기준일 이름|포지션"이며 값은 KBO 공식 playerId다.
$manualOverrides = @{
    "KIA 타이거즈|김현수|P" = "69516"
    "KT 위즈|배재성|P" = "65516"
    "LG 트윈스|최채흥|P" = "68419"
    "NC 다이노스|김민규|P" = "54913"
    "롯데 자이언츠|정훈|IF" = "60523"
    "삼성 라이온즈|이상민|P" = "63960"
    "한화 이글스|박준영|P" = "52731"
    "한화 이글스|이태양|P" = "60768"
    "한화 이글스|장지수|P" = "69645"
    "KT 위즈|김상수|IF" = "79402"
    "롯데 자이언츠|김상수|P" = "76430"
    "KT 위즈|박민석|IF" = "69056"
    "KT 위즈|박민석|OF" = "55004"
}

$roster = @(Import-Csv -Encoding UTF8 $RosterPath)
$candidates = @(
    Import-Csv -Encoding UTF8 $CandidatePath |
        Sort-Object kbo_player_id -Unique
)
$matches = [System.Collections.Generic.List[object]]::new()
$reviews = [System.Collections.Generic.List[object]]::new()

$rosterGroups = @($roster | Group-Object team, name, position_group)
foreach ($group in $rosterGroups) {
    $rows = @($group.Group | Sort-Object source_uid)
    $sample = $rows[0]
    $overrideKey = "$($sample.team)|$($sample.name)|$($sample.position_group)"
    $positionName = $positionNames[$sample.position_group]
    $sameName = @($candidates | Where-Object { $_.name -eq $sample.name })
    $possible = @(
        $sameName | Where-Object { $_.position_name -eq $positionName }
    )
    $exactTeamName = @(
        $sameName | Where-Object {
            $teamNames.ContainsKey($_.team_name) -and $teamNames[$_.team_name] -eq $sample.team
        }
    )
    $exactTeam = @(
        $possible | Where-Object {
            $teamNames.ContainsKey($_.team_name) -and $teamNames[$_.team_name] -eq $sample.team
        }
    )
    $currentName = @($sameName | Where-Object candidate_status -eq "now")
    $current = @($possible | Where-Object candidate_status -eq "now")

    $selected = @()
    $method = ""
    if ($manualOverrides.ContainsKey($overrideKey) -and $rows.Count -eq 1) {
        $overrideId = $manualOverrides[$overrideKey]
        $knownCandidate = @($candidates | Where-Object kbo_player_id -eq $overrideId | Select-Object -First 1)
        $detailType = if ($sample.position_group -eq "P") { "Pitcher" } else { "Hitter" }
        $selected = @([pscustomobject]@{
            kbo_player_id = $overrideId
            candidate_status = if ($knownCandidate.Count) { $knownCandidate[0].candidate_status } else { "manual" }
            team_name = if ($knownCandidate.Count) { $knownCandidate[0].team_name } else { "" }
            bats_throws = if ($knownCandidate.Count) { $knownCandidate[0].bats_throws } else { "" }
            profile_link = "/Record/Player/$($detailType)Detail/Basic.aspx?playerId=$overrideId"
        })
        $method = "manual_official_id"
    }
    elseif ($exactTeamName.Count -eq $rows.Count) {
        $selected = @($exactTeamName | Sort-Object kbo_player_id)
        $method = "exact_team_name"
    }
    elseif ($exactTeam.Count -eq $rows.Count) {
        $selected = @($exactTeam | Sort-Object kbo_player_id)
        $method = "exact_team_name_position"
    }
    elseif ($exactTeamName.Count -eq 0 -and $currentName.Count -eq $rows.Count) {
        $selected = @($currentName | Sort-Object kbo_player_id)
        $method = "current_name"
    }
    elseif ($exactTeam.Count -eq 0 -and $current.Count -eq $rows.Count) {
        $selected = @($current | Sort-Object kbo_player_id)
        $method = "current_name_position"
    }
    elseif ($exactTeam.Count -eq 0 -and $possible.Count -eq $rows.Count) {
        $selected = @($possible | Sort-Object kbo_player_id)
        $method = "unique_name_position"
    }

    if ($selected.Count -eq $rows.Count) {
        for ($index = 0; $index -lt $rows.Count; $index++) {
            $row = $rows[$index]
            $candidate = $selected[$index]
            $matches.Add([pscustomobject]@{
                source_uid = $row.source_uid
                snapshot_team = $row.team
                snapshot_name = $row.name
                position_group = $row.position_group
                kbo_player_id = $candidate.kbo_player_id
                candidate_status = $candidate.candidate_status
                candidate_team = $candidate.team_name
                bats_throws = $candidate.bats_throws
                profile_link = $candidate.profile_link
                match_method = $method
            })
        }
    }
    else {
        $reviews.Add([pscustomobject]@{
            source_uids = ($rows.source_uid -join "|")
            snapshot_team = $sample.team
            snapshot_name = $sample.name
            position_group = $sample.position_group
            roster_count = $rows.Count
            possible_count = $possible.Count
            same_name_count = $sameName.Count
            exact_team_name_count = $exactTeamName.Count
            exact_team_count = $exactTeam.Count
            current_name_count = $currentName.Count
            current_count = $current.Count
            candidate_ids = (@($possible | ForEach-Object { $_.kbo_player_id }) -join "|")
            candidate_teams = (@($possible | ForEach-Object { $_.team_name }) -join "|")
            candidate_statuses = (@($possible | ForEach-Object { $_.candidate_status }) -join "|")
        })
    }
}

$matches | Sort-Object snapshot_team, snapshot_name, source_uid | Export-Csv $MatchedPath -NoTypeInformation -Encoding UTF8
$reviews | Sort-Object snapshot_team, snapshot_name | Export-Csv $ReviewPath -NoTypeInformation -Encoding UTF8

$reviewPlayers = if ($reviews.Count -eq 0) { 0 } else { ($reviews | Measure-Object roster_count -Sum).Sum }
Write-Output "ROSTER=$($roster.Count) MATCHED=$($matches.Count) REVIEW_ROWS=$($reviews.Count) REVIEW_PLAYERS=$reviewPlayers"
$matches | Group-Object match_method | Sort-Object Name | Select-Object Name, Count
if ($reviews.Count -gt 0) { $reviews | Format-Table -AutoSize }
