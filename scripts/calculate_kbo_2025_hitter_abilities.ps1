param(
    [string]$FirstTeamPath = "data/source/kbo_2025_first_team_hitting.csv",
    [string]$FuturesPath = "data/source/kbo_2025_futures_hitting.csv",
    [string]$SituationPath = "data/source/kbo_2025_hitter_situation_splits.csv",
    [string]$RunningPath = "data/source/kbo_2025_running.csv",
    [string]$OutputPath = "data/source/kbo_2025_hitter_abilities.csv"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$culture = [System.Globalization.CultureInfo]::InvariantCulture
$formulaVersion = "kbo-hitter-abilities-v2-compressed"

function Test-Number {
    param([object]$Value)
    return ([string]$Value) -match '^-?\d+(?:\.\d+)?$'
}

function Get-Int {
    param([object]$Value)
    if (Test-Number $Value) { return [int]$Value }
    return 0
}

function Get-Percentile {
    param([object]$Values, [double]$Value)
    if ($Values.Count -eq 0) { return 0.5 }
    $less = 0
    $equal = 0
    foreach ($candidate in $Values) {
        if ([double]$candidate -lt $Value) { $less++ }
        elseif ([Math]::Abs([double]$candidate - $Value) -lt 0.0000000001) { $equal++ }
    }
    return ($less + 0.5 * $equal) / $Values.Count
}

function Convert-ToRating {
    param([double]$Percentile, [int]$Adjustment = 0)
    $rating = if ($Percentile -lt 0.001) { 1 }
        elseif ($Percentile -lt 0.003) { 2 }
        elseif ($Percentile -lt 0.010) { 3 }
        elseif ($Percentile -lt 0.025) { 4 }
        elseif ($Percentile -lt 0.050) { 5 }
        elseif ($Percentile -lt 0.100) { 6 }
        elseif ($Percentile -lt 0.170) { 7 }
        elseif ($Percentile -lt 0.250) { 8 }
        elseif ($Percentile -lt 0.370) { 9 }
        elseif ($Percentile -lt 0.550) { 10 }
        elseif ($Percentile -lt 0.650) { 11 }
        elseif ($Percentile -lt 0.750) { 12 }
        elseif ($Percentile -lt 0.840) { 13 }
        elseif ($Percentile -lt 0.900) { 14 }
        elseif ($Percentile -lt 0.950) { 15 }
        elseif ($Percentile -lt 0.975) { 16 }
        elseif ($Percentile -lt 0.990) { 17 }
        elseif ($Percentile -lt 0.997) { 18 }
        elseif ($Percentile -lt 0.9995) { 19 }
        else { 20 }
    $rating += $Adjustment
    return [Math]::Max(1, [Math]::Min(20, $rating))
}

function Get-Confidence {
    param([int]$Sample)
    if ($Sample -ge 300) { return "high" }
    if ($Sample -ge 100) { return "medium" }
    if ($Sample -ge 30) { return "low" }
    if ($Sample -gt 0) { return "very_low" }
    return "none"
}

function New-BattingModel {
    param([object]$Row)
    $ab = Get-Int $Row.AB
    $pa = Get-Int $Row.PA
    $h = Get-Int $Row.H
    $doubles = Get-Int $Row."2B"
    $triples = Get-Int $Row."3B"
    $hr = Get-Int $Row.HR
    return [pscustomobject]@{
        Id = [string]$Row.kbo_player_id
        PA = $pa
        AB = $ab
        H = $h
        Doubles = $doubles
        Triples = $triples
        HR = $hr
        ExtraBases = $doubles + 2 * $triples + 3 * $hr
        BB = Get-Int $Row.BB
        HBP = Get-Int $Row.HBP
        SO = Get-Int $Row.SO
        SB = Get-Int $Row.SB
        CS = Get-Int $Row.CS
        SAC = if ($Row.PSObject.Properties.Name -contains "SAC") { Get-Int $Row.SAC } else { 0 }
    }
}

function Add-BattingPercentiles {
    param([object]$Models)
    $totalAB = 0; $totalPA = 0; $totalH = 0; $totalXB = 0; $totalHR = 0; $totalBB = 0; $totalSO = 0
    foreach ($model in $Models) {
        $totalAB += $model.AB; $totalPA += $model.PA; $totalH += $model.H
        $totalXB += $model.ExtraBases; $totalHR += $model.HR; $totalBB += $model.BB; $totalSO += $model.SO
    }
    $priorAVG = if ($totalAB -gt 0) { $totalH / $totalAB } else { 0.250 }
    $priorISO = if ($totalAB -gt 0) { $totalXB / $totalAB } else { 0.120 }
    $priorHR = if ($totalPA -gt 0) { $totalHR / $totalPA } else { 0.020 }
    $priorBB = if ($totalPA -gt 0) { $totalBB / $totalPA } else { 0.080 }
    $priorK = if ($totalPA -gt 0) { $totalSO / $totalPA } else { 0.180 }
    $avgValues = [System.Collections.Generic.List[double]]::new()
    $isoValues = [System.Collections.Generic.List[double]]::new()
    $hrValues = [System.Collections.Generic.List[double]]::new()
    $bbValues = [System.Collections.Generic.List[double]]::new()
    $kValues = [System.Collections.Generic.List[double]]::new()
    foreach ($model in $Models) {
        $model | Add-Member AdjustedAVG (($model.H + $priorAVG * 100) / ($model.AB + 100))
        $model | Add-Member AdjustedISO (($model.ExtraBases + $priorISO * 100) / ($model.AB + 100))
        $model | Add-Member AdjustedHRRate (($model.HR + $priorHR * 100) / ($model.PA + 100))
        $model | Add-Member AdjustedBBRate (($model.BB + $priorBB * 100) / ($model.PA + 100))
        $model | Add-Member AdjustedKRate (($model.SO + $priorK * 100) / ($model.PA + 100))
        $avgValues.Add($model.AdjustedAVG); $isoValues.Add($model.AdjustedISO); $hrValues.Add($model.AdjustedHRRate)
        $bbValues.Add($model.AdjustedBBRate); $kValues.Add($model.AdjustedKRate)
    }
    foreach ($model in $Models) {
        $avgPct = Get-Percentile $avgValues $model.AdjustedAVG
        $isoPct = Get-Percentile $isoValues $model.AdjustedISO
        $hrPct = Get-Percentile $hrValues $model.AdjustedHRRate
        $bbPct = Get-Percentile $bbValues $model.AdjustedBBRate
        $kGoodPct = 1 - (Get-Percentile $kValues $model.AdjustedKRate)
        $abReliability = $model.AB / ($model.AB + 100.0)
        $paReliability = $model.PA / ($model.PA + 100.0)
        $model | Add-Member ContactPct (0.5 + ($avgPct - 0.5) * $abReliability)
        $isoEvidencePct = 0.5 + ($isoPct - 0.5) * $abReliability
        $hrEvidencePct = 0.5 + ($hrPct - 0.5) * $paReliability
        $model | Add-Member PowerPct (0.70 * $isoEvidencePct + 0.30 * $hrEvidencePct)
        $model | Add-Member EyePct (0.5 + ($bbPct - 0.5) * $paReliability)
        $model | Add-Member BatControlPct (0.5 + ($kGoodPct - 0.5) * $paReliability)
    }
}

function Add-RunningPercentiles {
    param([object]$Models, [bool]$HasOutData)
    $totalOpp = 0; $totalAB = 0; $totalSBA = 0; $totalSB = 0; $totalTriples = 0; $totalOOB = 0; $totalPKO = 0
    foreach ($model in $Models) {
        $totalOpp += $model.Opp; $totalAB += $model.AB; $totalSBA += $model.SBA
        $totalSB += $model.SB; $totalTriples += $model.Triples; $totalOOB += $model.OOB; $totalPKO += $model.PKO
    }
    $priorAttempt = if ($totalOpp -gt 0) { $totalSBA / $totalOpp } else { 0.080 }
    $priorTriple = if ($totalAB -gt 0) { $totalTriples / $totalAB } else { 0.004 }
    $priorSuccess = if ($totalSBA -gt 0) { $totalSB / $totalSBA } else { 0.750 }
    $priorOOB = if ($totalOpp -gt 0) { $totalOOB / $totalOpp } else { 0.025 }
    $priorPKO = if ($totalOpp -gt 0) { $totalPKO / $totalOpp } else { 0.004 }
    $attemptValues = [System.Collections.Generic.List[double]]::new()
    $tripleValues = [System.Collections.Generic.List[double]]::new()
    $successValues = [System.Collections.Generic.List[double]]::new()
    $oobValues = [System.Collections.Generic.List[double]]::new()
    $pkoValues = [System.Collections.Generic.List[double]]::new()
    foreach ($model in $Models) {
        $model | Add-Member AdjustedAttemptRate (($model.SBA + $priorAttempt * 50) / ($model.Opp + 50))
        $model | Add-Member AdjustedTripleRate (($model.Triples + $priorTriple * 100) / ($model.AB + 100))
        $model | Add-Member AdjustedSBPct (($model.SB + $priorSuccess * 10) / ($model.SBA + 10))
        $model | Add-Member AdjustedOOBRate (($model.OOB + $priorOOB * 50) / ($model.Opp + 50))
        $model | Add-Member AdjustedPKORate (($model.PKO + $priorPKO * 50) / ($model.Opp + 50))
        $attemptValues.Add($model.AdjustedAttemptRate); $tripleValues.Add($model.AdjustedTripleRate)
        $successValues.Add($model.AdjustedSBPct); $oobValues.Add($model.AdjustedOOBRate); $pkoValues.Add($model.AdjustedPKORate)
    }
    foreach ($model in $Models) {
        $attemptPct = Get-Percentile $attemptValues $model.AdjustedAttemptRate
        $triplePct = Get-Percentile $tripleValues $model.AdjustedTripleRate
        $successPct = Get-Percentile $successValues $model.AdjustedSBPct
        $oppReliability = $model.Opp / ($model.Opp + 50.0)
        $abReliability = $model.AB / ($model.AB + 100.0)
        $sbaReliability = $model.SBA / ($model.SBA + 10.0)
        $attemptEvidencePct = 0.5 + ($attemptPct - 0.5) * $oppReliability
        $tripleEvidencePct = 0.5 + ($triplePct - 0.5) * $abReliability
        $successEvidencePct = 0.5 + ($successPct - 0.5) * $sbaReliability
        $model | Add-Member SpeedPct (0.70 * $attemptEvidencePct + 0.30 * $tripleEvidencePct)
        if ($HasOutData) {
            $oobGoodPct = 1 - (Get-Percentile $oobValues $model.AdjustedOOBRate)
            $pkoGoodPct = 1 - (Get-Percentile $pkoValues $model.AdjustedPKORate)
            $oobEvidencePct = 0.5 + ($oobGoodPct - 0.5) * $oppReliability
            $pkoEvidencePct = 0.5 + ($pkoGoodPct - 0.5) * $oppReliability
            $model | Add-Member JudgmentPct (0.55 * $successEvidencePct + 0.30 * $oobEvidencePct + 0.15 * $pkoEvidencePct)
        }
        else {
            $model | Add-Member JudgmentPct (0.70 * $successEvidencePct + 0.30 * 0.5)
        }
    }
}

$firstRows = @(Import-Csv -Encoding UTF8 $FirstTeamPath)
$futuresRows = @(Import-Csv -Encoding UTF8 $FuturesPath)
$runningRows = @(Import-Csv -Encoding UTF8 $RunningPath)
$situationRows = @(Import-Csv -Encoding UTF8 $SituationPath)
if ($firstRows.Count -ne 317 -or $futuresRows.Count -ne 317 -or $runningRows.Count -ne 317) {
    throw "Expected 317 rows in first-team, Futures, and running sources."
}

$firstById = @{}; $futuresById = @{}; $runningById = @{}
foreach ($row in $firstRows) { $firstById[$row.kbo_player_id] = $row }
foreach ($row in $futuresRows) { $futuresById[$row.kbo_player_id] = $row }
foreach ($row in $runningRows) { $runningById[$row.kbo_player_id] = $row }

$firstModels = [System.Collections.Generic.List[object]]::new()
$futuresModels = [System.Collections.Generic.List[object]]::new()
foreach ($row in $firstRows) {
    if ((Get-Int $row.PA) -gt 0) { $firstModels.Add((New-BattingModel $row)) }
}
foreach ($row in $futuresRows) {
    if ((Get-Int $row.PA) -gt 0) { $futuresModels.Add((New-BattingModel $row)) }
}
Add-BattingPercentiles $firstModels
Add-BattingPercentiles $futuresModels
$firstModelById = @{}; $futuresModelById = @{}
foreach ($model in $firstModels) { $firstModelById[$model.Id] = $model }
foreach ($model in $futuresModels) { $futuresModelById[$model.Id] = $model }

# Pitcher-type timing uses equal weight for each published pitcher type. Small split samples
# are regressed toward the split-specific league AVG and K rate with 30 pseudo opportunities.
$splitGroups = @{}
foreach ($row in $situationRows) {
    if ($row.split_category -ne "pitcher_type") { continue }
    if (-not $splitGroups.ContainsKey($row.split_label)) { $splitGroups[$row.split_label] = [System.Collections.Generic.List[object]]::new() }
    $splitGroups[$row.split_label].Add([pscustomobject]@{
        Id = [string]$row.kbo_player_id
        AB = Get-Int $row.AB
        H = Get-Int $row.H
        BB = Get-Int $row.BB
        HBP = Get-Int $row.HBP
        SO = Get-Int $row.SO
    })
}
$timingPartsById = @{}; $timingAbById = @{}
foreach ($entry in $splitGroups.GetEnumerator()) {
    $group = $entry.Value
    $totalAB = 0; $totalH = 0; $totalOpp = 0; $totalSO = 0
    foreach ($split in $group) { $totalAB += $split.AB; $totalH += $split.H; $totalOpp += $split.AB + $split.BB + $split.HBP; $totalSO += $split.SO }
    $priorAVG = if ($totalAB -gt 0) { $totalH / $totalAB } else { 0.250 }
    $priorK = if ($totalOpp -gt 0) { $totalSO / $totalOpp } else { 0.180 }
    $avgValues = [System.Collections.Generic.List[double]]::new(); $kValues = [System.Collections.Generic.List[double]]::new()
    foreach ($split in $group) {
        $split | Add-Member AdjustedAVG (($split.H + $priorAVG * 30) / ($split.AB + 30))
        $opportunities = $split.AB + $split.BB + $split.HBP
        $split | Add-Member AdjustedK (($split.SO + $priorK * 30) / ($opportunities + 30))
        $avgValues.Add($split.AdjustedAVG); $kValues.Add($split.AdjustedK)
    }
    foreach ($split in $group) {
        $avgPct = Get-Percentile $avgValues $split.AdjustedAVG
        $kGoodPct = 1 - (Get-Percentile $kValues $split.AdjustedK)
        $opportunities = $split.AB + $split.BB + $split.HBP
        $avgReliability = $split.AB / ($split.AB + 30.0)
        $kReliability = $opportunities / ($opportunities + 30.0)
        $avgEvidencePct = 0.5 + ($avgPct - 0.5) * $avgReliability
        $kEvidencePct = 0.5 + ($kGoodPct - 0.5) * $kReliability
        $part = 0.70 * $avgEvidencePct + 0.30 * $kEvidencePct
        if (-not $timingPartsById.ContainsKey($split.Id)) { $timingPartsById[$split.Id] = [System.Collections.Generic.List[double]]::new(); $timingAbById[$split.Id] = 0 }
        $timingPartsById[$split.Id].Add($part); $timingAbById[$split.Id] += $split.AB
    }
}
$timingTypeCount = $splitGroups.Count

$firstRunModels = [System.Collections.Generic.List[object]]::new()
foreach ($row in $runningRows) {
    if ($row.has_record -ne "1") { continue }
    $hitting = $firstById[$row.kbo_player_id]
    $opp = (Get-Int $hitting.H) + (Get-Int $hitting.BB) + (Get-Int $hitting.HBP) - (Get-Int $hitting.HR)
    $firstRunModels.Add([pscustomobject]@{
        Id = [string]$row.kbo_player_id
        Opp = $opp
        AB = Get-Int $hitting.AB
        Triples = Get-Int $hitting."3B"
        SBA = Get-Int $row.SBA
        SB = Get-Int $row.SB
        OOB = Get-Int $row.OOB
        PKO = Get-Int $row.PKO
    })
}
Add-RunningPercentiles $firstRunModels $true
$firstRunById = @{}; foreach ($model in $firstRunModels) { $firstRunById[$model.Id] = $model }

$futuresRunModels = [System.Collections.Generic.List[object]]::new()
foreach ($row in $futuresRows) {
    if ((Get-Int $row.PA) -le 0) { continue }
    $opp = (Get-Int $row.H) + (Get-Int $row.BB) + (Get-Int $row.HBP) - (Get-Int $row.HR)
    $sb = Get-Int $row.SB; $cs = Get-Int $row.CS
    $futuresRunModels.Add([pscustomobject]@{
        Id = [string]$row.kbo_player_id
        Opp = $opp
        AB = Get-Int $row.AB
        Triples = Get-Int $row."3B"
        SBA = $sb + $cs
        SB = $sb
        OOB = 0
        PKO = 0
    })
}
Add-RunningPercentiles $futuresRunModels $false
$futuresRunById = @{}; foreach ($model in $futuresRunModels) { $futuresRunById[$model.Id] = $model }

$positiveSac = @($firstModels | Where-Object SAC -gt 0 | ForEach-Object { [double]$_.SAC })
$output = foreach ($rosterRow in $firstRows) {
    $id = [string]$rosterRow.kbo_player_id
    $sourceLevel = "none"; $levelAdjustment = 0; $model = $null; $runModel = $null; $timingPct = 0.5; $timingSource = "unavailable"
    if ($firstModelById.ContainsKey($id)) {
        $sourceLevel = "KBO"
        $model = $firstModelById[$id]
        $runModel = $firstRunById[$id]
        if ($timingPartsById.ContainsKey($id)) {
            $parts = $timingPartsById[$id]
            $sum = 0.0; foreach ($part in $parts) { $sum += $part }
            $timingPct = ($sum + 0.5 * ($timingTypeCount - $parts.Count)) / $timingTypeCount
            $timingSource = "kbo_pitcher_type_splits"
        }
    }
    elseif ($futuresModelById.ContainsKey($id)) {
        $sourceLevel = "FUTURES"
        $levelAdjustment = -2
        $model = $futuresModelById[$id]
        $runModel = $futuresRunById[$id]
        $timingPct = 0.60 * $model.ContactPct + 0.40 * $model.BatControlPct
        $timingSource = "futures_contact_k_proxy"
    }

    if ($null -eq $model) {
        $contact = 10; $power = 10; $eye = 10; $batControl = 10; $timing = 10; $bunt = 1
        $speed = 10; $judgment = 10; $pa = 0; $ab = 0; $sba = 0; $oob = ""; $pko = ""
        $contactPct = 0.5; $powerPct = 0.5; $eyePct = 0.5; $batControlPct = 0.5; $speedPct = 0.5; $judgmentPct = 0.5
        $adjustedAVG = ""; $adjustedISO = ""; $adjustedHR = ""; $adjustedBB = ""; $adjustedK = ""
        $adjustedAttempt = ""; $adjustedSBPct = ""; $adjustedOOB = ""; $adjustedPKO = ""
    }
    else {
        $contact = Convert-ToRating $model.ContactPct $levelAdjustment
        $power = Convert-ToRating $model.PowerPct $levelAdjustment
        $eye = Convert-ToRating $model.EyePct $levelAdjustment
        $batControl = Convert-ToRating $model.BatControlPct $levelAdjustment
        $timing = Convert-ToRating $timingPct $levelAdjustment
        if ($sourceLevel -eq "KBO" -and $model.SAC -gt 0) {
            $sacPct = Get-Percentile $positiveSac ([double]$model.SAC)
            $reliability = $model.SAC / ($model.SAC + 5.0)
            $bunt = [Math]::Max(4, [Math]::Min(20, [int][Math]::Round(3 + 17 * $sacPct * $reliability)))
        } else { $bunt = 1 }
        $speed = if ($null -ne $runModel) { Convert-ToRating $runModel.SpeedPct $levelAdjustment } else { 10 }
        $judgment = if ($null -ne $runModel) { Convert-ToRating $runModel.JudgmentPct $levelAdjustment } else { 10 }
        $pa = $model.PA; $ab = $model.AB; $sba = if ($null -ne $runModel) { $runModel.SBA } else { 0 }
        $oob = if ($sourceLevel -eq "KBO" -and $null -ne $runModel) { $runModel.OOB } else { "" }
        $pko = if ($sourceLevel -eq "KBO" -and $null -ne $runModel) { $runModel.PKO } else { "" }
        $contactPct = $model.ContactPct; $powerPct = $model.PowerPct; $eyePct = $model.EyePct; $batControlPct = $model.BatControlPct
        $speedPct = if ($null -ne $runModel) { $runModel.SpeedPct } else { 0.5 }
        $judgmentPct = if ($null -ne $runModel) { $runModel.JudgmentPct } else { 0.5 }
        $adjustedAVG = $model.AdjustedAVG; $adjustedISO = $model.AdjustedISO; $adjustedHR = $model.AdjustedHRRate
        $adjustedBB = $model.AdjustedBBRate; $adjustedK = $model.AdjustedKRate
        $adjustedAttempt = if ($null -ne $runModel) { $runModel.AdjustedAttemptRate } else { "" }
        $adjustedSBPct = if ($null -ne $runModel) { $runModel.AdjustedSBPct } else { "" }
        $adjustedOOB = if ($sourceLevel -eq "KBO" -and $null -ne $runModel) { $runModel.AdjustedOOBRate } else { "" }
        $adjustedPKO = if ($sourceLevel -eq "KBO" -and $null -ne $runModel) { $runModel.AdjustedPKORate } else { "" }
    }

    [pscustomobject][ordered]@{
        season = "2025"
        kbo_player_id = $id
        player_uid = $rosterRow.player_uid
        snapshot_team = $rosterRow.snapshot_team
        player_name = $rosterRow.player_name
        position_group = $rosterRow.position_group
        source_level = $sourceLevel
        level_adjustment = $levelAdjustment
        PA = $pa
        AB = $ab
        SBA = $sba
        OOB = $oob
        PKO = $pko
        contact = $contact
        power = $power
        plate_discipline = $eye
        bat_control = $batControl
        timing = $timing
        bunt = $bunt
        speed = $speed
        baserunning_judgment = $judgment
        contact_percentile = ([double]$contactPct).ToString("0.0000", $culture)
        power_percentile = ([double]$powerPct).ToString("0.0000", $culture)
        plate_discipline_percentile = ([double]$eyePct).ToString("0.0000", $culture)
        bat_control_percentile = ([double]$batControlPct).ToString("0.0000", $culture)
        timing_percentile = ([double]$timingPct).ToString("0.0000", $culture)
        speed_percentile = ([double]$speedPct).ToString("0.0000", $culture)
        baserunning_judgment_percentile = ([double]$judgmentPct).ToString("0.0000", $culture)
        adjusted_avg = if ($adjustedAVG -ne "") { ([double]$adjustedAVG).ToString("0.0000", $culture) } else { "" }
        adjusted_iso = if ($adjustedISO -ne "") { ([double]$adjustedISO).ToString("0.0000", $culture) } else { "" }
        adjusted_hr_rate = if ($adjustedHR -ne "") { ([double]$adjustedHR).ToString("0.0000", $culture) } else { "" }
        adjusted_bb_rate = if ($adjustedBB -ne "") { ([double]$adjustedBB).ToString("0.0000", $culture) } else { "" }
        adjusted_k_rate = if ($adjustedK -ne "") { ([double]$adjustedK).ToString("0.0000", $culture) } else { "" }
        adjusted_sba_rate = if ($adjustedAttempt -ne "") { ([double]$adjustedAttempt).ToString("0.0000", $culture) } else { "" }
        adjusted_sb_pct = if ($adjustedSBPct -ne "") { ([double]$adjustedSBPct).ToString("0.0000", $culture) } else { "" }
        adjusted_oob_rate = if ($adjustedOOB -ne "") { ([double]$adjustedOOB).ToString("0.0000", $culture) } else { "" }
        adjusted_pko_rate = if ($adjustedPKO -ne "") { ([double]$adjustedPKO).ToString("0.0000", $culture) } else { "" }
        batting_confidence = Get-Confidence $pa
        running_confidence = Get-Confidence $(if ($null -ne $runModel) { $runModel.Opp } else { 0 })
        timing_source = $timingSource
        timing_split_ab = if ($timingAbById.ContainsKey($id)) { $timingAbById[$id] } else { 0 }
        fielding_range = ""
        catching = ""
        throwing_power = ""
        throwing_accuracy = ""
        fielding_judgment = ""
        composure = ""
        leadership = ""
        aggressiveness = ""
        formula_version = $formulaVersion
    }
}

if ($output.Count -ne 317) { throw "Expected 317 ability rows, got $($output.Count)." }
foreach ($row in $output) {
    foreach ($field in @("contact", "power", "plate_discipline", "bat_control", "timing", "speed", "baserunning_judgment")) {
        if ([int]$row.$field -lt 1 -or [int]$row.$field -gt 20) { throw "Rating out of range: $($row.kbo_player_id) $field=$($row.$field)" }
    }
    if ([int]$row.bunt -lt 0 -or [int]$row.bunt -gt 20) { throw "Bunt out of range: $($row.kbo_player_id)" }
}
$output | Sort-Object snapshot_team, player_name, kbo_player_id | Export-Csv $OutputPath -NoTypeInformation -Encoding UTF8
$sourceCounts = $output | Group-Object source_level | ForEach-Object { "$($_.Name)=$($_.Count)" }
Write-Output "COMPLETE rows=$($output.Count) $($sourceCounts -join ' ') formula=$formulaVersion"
