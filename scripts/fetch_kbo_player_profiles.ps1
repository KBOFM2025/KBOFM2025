param(
    [string]$RosterPath = "data/source/kbo_2025_roster_2025-10-31.csv",
    [string]$MatchPath = "data/source/kbo_2025_profile_matches.csv",
    [string]$ProfilePath = "data/source/kbo_2025_player_profiles.csv",
    [string]$FinalRosterPath = "data/source/kbo_2025_final_roster.csv",
    [int]$BatchSize = 6
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.Net.Http

function Read-ProfileField {
    param([string]$Html, [string]$Field)
    $pattern = '<span[^>]+id="[^"]*playerProfile_' + [regex]::Escape($Field) + '"[^>]*>(.*?)</span>'
    $match = [regex]::Match($Html, $pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    if (-not $match.Success) { return "" }
    $withoutTags = [regex]::Replace($match.Groups[1].Value, '<[^>]+>', '')
    return [System.Net.WebUtility]::HtmlDecode($withoutTags).Trim()
}

$roster = @(Import-Csv -Encoding UTF8 $RosterPath)
$matches = @(Import-Csv -Encoding UTF8 $MatchPath)
if ($roster.Count -ne 636 -or $matches.Count -ne 636) {
    throw "Expected 636 roster and match rows; got roster=$($roster.Count), matches=$($matches.Count)."
}
if (@($matches.kbo_player_id | Sort-Object -Unique).Count -ne 636) {
    throw "KBO player IDs must be unique."
}

$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate
$client = [System.Net.Http.HttpClient]::new($handler)
$client.BaseAddress = [uri]"https://www.koreabaseball.com"
$client.DefaultRequestHeaders.Referrer = [uri]"https://www.koreabaseball.com/Player/Search.aspx"
$client.Timeout = [timespan]::FromSeconds(30)
$profiles = [System.Collections.Generic.List[object]]::new()
$errors = [System.Collections.Generic.List[string]]::new()
$snapshotDate = [datetime]"2025-10-31"

try {
    for ($batchStart = 0; $batchStart -lt $matches.Count; $batchStart += $BatchSize) {
        $pending = [System.Collections.Generic.List[object]]::new()
        $batchEnd = [Math]::Min($batchStart + $BatchSize, $matches.Count)
        for ($index = $batchStart; $index -lt $batchEnd; $index++) {
            $row = $matches[$index]
            $detailType = if ($row.position_group -eq "P") { "Pitcher" } else { "Hitter" }
            $path = "/Record/Player/$($detailType)Detail/Basic.aspx?playerId=$($row.kbo_player_id)"
            $pending.Add([pscustomobject]@{
                Row = $row
                Path = $path
                Task = $client.GetAsync($path)
            })
        }

        foreach ($request in $pending) {
            try {
                $response = $request.Task.Result
                $response.EnsureSuccessStatusCode() | Out-Null
                $html = $response.Content.ReadAsStringAsync().Result
                $profileName = Read-ProfileField $html "lblName"
                $birthdayText = Read-ProfileField $html "lblBirthday"
                $positionText = Read-ProfileField $html "lblPosition"
                $heightWeight = Read-ProfileField $html "lblHeightWeight"
                $career = Read-ProfileField $html "lblCareer"

                $birthdayMatch = [regex]::Match($birthdayText, '^(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일$')
                if (-not $birthdayMatch.Success) { throw "Missing birthday ($birthdayText)" }
                $birthDate = [datetime]::new(
                    [int]$birthdayMatch.Groups[1].Value,
                    [int]$birthdayMatch.Groups[2].Value,
                    [int]$birthdayMatch.Groups[3].Value
                )
                $age = $snapshotDate.Year - $birthDate.Year
                if ($birthDate.Date -gt $snapshotDate.AddYears(-$age).Date) { $age-- }

                $positionMatch = [regex]::Match($positionText, '^(.*?)\((.*?)\)$')
                $heightWeightMatch = [regex]::Match($heightWeight, '^(\d+)cm/(\d+)kg$')
                $profiles.Add([pscustomobject]@{
                    source_uid = $request.Row.source_uid
                    kbo_player_id = $request.Row.kbo_player_id
                    snapshot_team = $request.Row.snapshot_team
                    snapshot_name = $request.Row.snapshot_name
                    profile_name = $profileName
                    birth_date = $birthDate.ToString("yyyy-MM-dd")
                    age = $age
                    position_name = if ($positionMatch.Success) { $positionMatch.Groups[1].Value } else { $positionText }
                    bats_throws = if ($positionMatch.Success) { $positionMatch.Groups[2].Value } else { $request.Row.bats_throws }
                    height_cm = if ($heightWeightMatch.Success) { [int]$heightWeightMatch.Groups[1].Value } else { $null }
                    weight_kg = if ($heightWeightMatch.Success) { [int]$heightWeightMatch.Groups[2].Value } else { $null }
                    career = $career
                    source_url = "https://www.koreabaseball.com$($request.Path)"
                })
            }
            catch {
                $errors.Add("$($request.Row.kbo_player_id) $($request.Row.snapshot_name): $($_.Exception.Message)")
            }
        }

        if ($batchEnd % 48 -eq 0 -or $batchEnd -eq $matches.Count) {
            Write-Output "FETCHED=$batchEnd/$($matches.Count) PROFILES=$($profiles.Count) ERRORS=$($errors.Count)"
        }
        Start-Sleep -Milliseconds 25
    }
}
finally {
    $client.Dispose()
    $handler.Dispose()
}

if ($errors.Count -gt 0) { throw "Profile failures: $($errors -join '; ')" }
$profiles | Sort-Object snapshot_team, snapshot_name, kbo_player_id | Export-Csv $ProfilePath -NoTypeInformation -Encoding UTF8

$profileByUid = @{}
foreach ($profile in $profiles) { $profileByUid[$profile.source_uid] = $profile }
$final = foreach ($row in $roster) {
    $profile = $profileByUid[$row.source_uid]
    if ($null -eq $profile) { throw "Missing joined profile: $($row.source_uid)" }
    [pscustomobject]@{
        snapshot_date = $row.snapshot_date
        kbo_player_id = $profile.kbo_player_id
        player_uid = "KBO-$($profile.kbo_player_id)"
        team = $row.team
        name = if ($row.team -eq "KT 위즈" -and $row.name -eq "배재성") { "배제성" } else { $row.name }
        profile_name = $profile.profile_name
        position_group = $row.position_group
        position_name = $profile.position_name
        birth_date = $profile.birth_date
        age = $profile.age
        bats_throws = $profile.bats_throws
        height_cm = $profile.height_cm
        weight_kg = $profile.weight_kg
        career = $profile.career
        is_rookie = $row.is_rookie
        is_foreign = $row.is_foreign
        membership_source = $row.membership_source
        last_movement_date = $row.last_movement_date
        last_movement_type = $row.last_movement_type
        source_note = $row.note
        source_url = $profile.source_url
    }
}
$final | Sort-Object team, position_group, name, kbo_player_id | Export-Csv $FinalRosterPath -NoTypeInformation -Encoding UTF8
Write-Output "COMPLETE: profiles=$($profiles.Count) final_roster=$(@($final).Count)"

