param(
    [string]$AbilityPath = "data/source/kbo_2025_hitter_abilities.csv",
    [string]$DefensePath = "data/source/kbo_2025_defense.csv",
    [string]$RosterPath = "data/source/kbo_2025_final_roster.csv",
    [string]$SalaryPath = "data/source/kbo_2025_verified_hitter_salaries.csv"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$formulaVersion = "kbo-hitter-abilities-v5-calibrated"

function Clamp([double]$Value, [double]$Minimum, [double]$Maximum) {
    return [Math]::Max($Minimum, [Math]::Min($Maximum, $Value))
}
function Number([object]$Value, [double]$Default = 0) {
    $parsed = 0.0
    if ([double]::TryParse([string]$Value, [ref]$parsed)) { return $parsed }
    return $Default
}
function Innings([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return 0.0 }
    if ($Value -match '^\s*(\d+)\s+([12])/3\s*$') { return [double]$Matches[1] + [double]$Matches[2] / 3.0 }
    return Number $Value 0
}
function Percentile([object[]]$Values, [double]$Value) {
    if ($Values.Count -eq 0) { return 0.5 }
    $less = 0; $equal = 0
    foreach ($candidate in $Values) {
        if ([double]$candidate -lt $Value) { $less++ }
        elseif ([Math]::Abs([double]$candidate - $Value) -lt 0.0000001) { $equal++ }
    }
    return ($less + 0.5 * $equal) / $Values.Count
}
function Rating([double]$Percentile, [int]$Adjustment = 0) {
    $cutoffs = @(0.001,0.003,0.010,0.025,0.050,0.100,0.170,0.250,0.370,0.550,0.650,0.750,0.840,0.900,0.950,0.975,0.990,0.997,0.9995)
    $rating = 20
    for ($index=0; $index -lt $cutoffs.Count; $index++) {
        if ($Percentile -lt $cutoffs[$index]) { $rating = $index + 1; break }
    }
    return [int](Clamp ($rating + $Adjustment) 1 20)
}
$abilities = @(Import-Csv -Encoding UTF8 $AbilityPath)
$defenseRows = @(Import-Csv -Encoding UTF8 $DefensePath)
$roster = @(Import-Csv -Encoding UTF8 $RosterPath | Where-Object position_group -ne 'P')
$salaryRows = @(Import-Csv -Encoding UTF8 $SalaryPath)
if ($abilities.Count -ne 317 -or $roster.Count -ne 317) { throw "Expected 317 hitters." }
$rosterById = @{}; foreach ($row in $roster) { $rosterById[[string]$row.kbo_player_id] = $row }
$salaryById = @{}
foreach ($row in $salaryRows) {
    $salaryId = [string]$row.kbo_player_id
    if (-not $rosterById.ContainsKey($salaryId)) { throw "Unknown salary player ID: $salaryId" }
    if ($salaryById.ContainsKey($salaryId)) { throw "Duplicate salary player ID: $salaryId" }
    $salaryById[$salaryId] = $row
}

# 포지션별 공식 기록을 동일 포지션 안에서 비교하고, 작은 표본은 리그 사전값으로 회귀시킨다.
$models = [System.Collections.Generic.List[object]]::new()
foreach ($row in $defenseRows) {
    $ip = Innings $row.IP
    if ($ip -le 0) { continue }
    $po=Number $row.PO; $a=Number $row.A; $e=Number $row.E; $dp=Number $row.DP
    $chances=$po+$a+$e; $group=[string]$row.position_group
    $models.Add([pscustomobject]@{
        Id=[string]$row.kbo_player_id; Position=$row.defense_position; Group=$group; IP=$ip
        Chances=$chances; Reliability=$ip/($ip+300.0)
        Range9=9.0*($po+$a)/$ip; Assist9=9.0*$a/$ip; DoublePlay9=9.0*$dp/$ip
        ErrorRate=($e+2.0)/(($chances)+200.0)
        PassedBall9=9.0*(Number $row.PB)/$ip
        CatchRate=((Number $row.CS)+3.0)/((Number $row.SB)+(Number $row.CS)+12.0)
    })
}

$groups = $models | Group-Object Position
foreach ($group in $groups) {
    $items=@($group.Group)
    $range=@($items.Range9); $assist=@($items.Assist9); $dp=@($items.DoublePlay9)
    $errorRates=@($items.ErrorRate); $pb=@($items.PassedBall9); $catch=@($items.CatchRate)
    foreach ($model in $items) {
        $rel=$model.Reliability
        $model | Add-Member RangePct (0.5 + ((Percentile $range $model.Range9)-0.5)*$rel)
        $model | Add-Member AssistPct (0.5 + ((Percentile $assist $model.Assist9)-0.5)*$rel)
        $model | Add-Member DpPct (0.5 + ((Percentile $dp $model.DoublePlay9)-0.5)*$rel)
        $model | Add-Member ErrorGoodPct (0.5 + ((1-(Percentile $errorRates $model.ErrorRate))-0.5)*$rel)
        $model | Add-Member PbGoodPct (0.5 + ((1-(Percentile $pb $model.PassedBall9))-0.5)*$rel)
        $model | Add-Member CatchPct (0.5 + ((Percentile $catch $model.CatchRate)-0.5)*$rel)
    }
}
$defenseById=@{}
foreach ($model in $models) {
    if (-not $defenseById.ContainsKey($model.Id)) { $defenseById[$model.Id]=[System.Collections.Generic.List[object]]::new() }
    $defenseById[$model.Id].Add($model)
}

$output = foreach ($ability in $abilities) {
    $id=[string]$ability.kbo_player_id; $profile=$rosterById[$id]
    $level=[string]$ability.source_level; $levelPenalty=if($level -eq 'FUTURES'){-2}elseif($level -eq 'none'){-3}else{0}
    $speed=Number $ability.speed 10; $eye=Number $ability.plate_discipline 10
    $control=Number $ability.bat_control 10; $timing=Number $ability.timing 10; $power=Number $ability.power 10
    $judgment=Number $ability.baserunning_judgment 10; $pa=Number $ability.PA 0; $age=Number $profile.age 25
    $positionName=[string]$profile.position_name; $positionGroup=[string]$profile.position_group
    $positionRange=if($positionGroup -eq 'OF'){11}elseif($positionGroup -eq 'IF'){10}elseif($positionGroup -eq 'C'){8}else{9}
    $positionCatch=if($positionGroup -eq 'C'){12}elseif($positionGroup -eq 'IF'){10}else{9}
    $positionArm=if($positionGroup -eq 'C'){12}elseif($positionGroup -in @('IF','OF')){10}else{8}

    $records=@(if($defenseById.ContainsKey($id)){$defenseById[$id]})
    if($records.Count -gt 0){
        $totalIp=($records|Measure-Object IP -Sum).Sum; $primary=$records|Sort-Object IP -Descending|Select-Object -First 1
        $rangePct=0.0;$catchPct=0.0;$armPct=0.0;$accuracyPct=0.0;$fieldIqPct=0.0
        foreach($record in $records){
            $weight=$record.IP/$totalIp
            $rangePart=0.72*$record.RangePct+0.28*(Clamp ($speed/20.0) 0.05 1)
            if($record.Group -eq 'C'){
                $catchPart=0.45*$record.ErrorGoodPct+0.25*$record.PbGoodPct+0.30*$record.CatchPct
                $armPart=0.75*$record.CatchPct+0.25*$record.AssistPct
            }else{
                $catchPart=0.72*$record.ErrorGoodPct+0.28*$record.RangePct
                $armPart=0.65*$record.AssistPct+0.35*$record.DpPct
            }
            $rangePct+=$weight*$rangePart; $catchPct+=$weight*$catchPart; $armPct+=$weight*$armPart
            $accuracyPct+=$weight*(0.78*$record.ErrorGoodPct+0.22*$record.AssistPct)
            $fieldIqPct+=$weight*(0.50*$record.ErrorGoodPct+0.30*$record.RangePct+0.20*$record.DpPct)
        }
        $fieldingRange=Rating $rangePct; $catching=Rating $catchPct; $throwingPower=Rating $armPct
        $throwingAccuracy=Rating $accuracyPct; $fieldingJudgment=Rating $fieldIqPct
        $defenseSource='KBO'; $defenseConfidence=if($totalIp-ge600){'high'}elseif($totalIp-ge250){'medium'}else{'low'}
        $defenseIp=[Math]::Round($totalIp,1); $primaryPosition=$primary.Position
    }else{
        # 공식 수비 표본이 없는 선수: 포지션 사전값 70% + 관측 가능한 운동·판단 특성 30%.
        $fieldingRange=[int](Clamp ([Math]::Round(0.70*$positionRange+0.30*$speed+$levelPenalty)) 1 20)
        $catching=[int](Clamp ([Math]::Round(0.75*$positionCatch+0.25*$control+$levelPenalty)) 1 20)
        $bodyArm=10+((Number $profile.height_cm 178)-178)/8.0+((Number $profile.weight_kg 80)-80)/18.0
        $throwingPower=[int](Clamp ([Math]::Round(0.75*$positionArm+0.25*$bodyArm+$levelPenalty)) 1 20)
        $throwingAccuracy=[int](Clamp ([Math]::Round(0.65*10+0.20*$control+0.15*$judgment+$levelPenalty)) 1 20)
        $fieldingJudgment=[int](Clamp ([Math]::Round(0.60*10+0.20*$judgment+0.20*$timing+$levelPenalty)) 1 20)
        $defenseSource=if($level -eq 'KBO'){'KBO_NO_FIELDING_SAMPLE'}else{'POSITION_PRIOR'}
        $defenseConfidence='very_low'; $defenseIp=0; $primaryPosition=$positionName
    }

    # 멘탈은 직접 관측 불가능하므로 표본 신뢰도만큼만 타격·상황 지표를 반영한다.
    $sampleDenominator=if($level -eq 'KBO'){250.0}else{450.0}
    $reliability=$pa/($pa+$sampleDenominator)
    $rawComposure=0.35*$eye+0.35*$control+0.20*$timing+0.10*$judgment
    $composure=[int](Clamp ([Math]::Round(10+($rawComposure-10)*$reliability+$levelPenalty)) 1 20)
    $experience=Clamp (($age-24)/3.0) -2 4
    $regularBonus=if([string]$profile.is_rookie -eq '1'){-1}elseif($pa-ge300){2}elseif($pa-ge100){1}else{0}
    $leadership=[int](Clamp ([Math]::Round(9+$experience+$regularBonus+$levelPenalty)) 1 20)
    $rawAggression=0.35*$power+0.25*$speed+0.25*$judgment+0.15*(21-$eye)
    $aggressiveness=[int](Clamp ([Math]::Round(10+($rawAggression-10)*(0.35+0.65*$reliability)+($levelPenalty/2.0))) 1 20)

    # Salary is a lagging market/reputation signal, never a replacement for direct
    # batting, running or fielding evidence.  Only an independently verified 2025
    # KBO salary may add one point to mental ratings.  Very-low-confidence fielding
    # judgment may receive the same one-point prior adjustment.
    $salaryAmount=''; $salarySource=''; $salaryPrior=''; $salaryAdjustment=0
    if($salaryById.ContainsKey($id)){
        $salaryRow=$salaryById[$id]; $salaryValue=Number $salaryRow.salary_10k_krw 0
        if($salaryValue -le 0){throw "Invalid salary: $id"}
        $isForeignSalary=([string]$salaryRow.coverage -eq 'foreign_contract_salary')
        if($isForeignSalary){
            # Foreign figures include signing bonuses, so use a separate baseline
            # and a weaker slope than domestic annual salaries.
            $prior=10.0+[Math]::Log($salaryValue/100000.0,2)*0.8
        }else{
            # Official 2025 domestic-player average: 160.71 million KRW.
            $prior=10.0+[Math]::Log($salaryValue/16071.0,2)*1.25
        }
        $prior=Clamp $prior 8 15
        $observedComposite=($control+$timing+$eye+$judgment+$fieldingJudgment+$composure)/6.0
        if($prior-$observedComposite -ge 2.0){$salaryAdjustment=1}
        if($salaryAdjustment -ne 0){
            $composure=[int](Clamp ($composure+$salaryAdjustment) 1 20)
            $leadership=[int](Clamp ($leadership+$salaryAdjustment) 1 20)
            if($defenseConfidence -eq 'very_low'){
                $fieldingJudgment=[int](Clamp ($fieldingJudgment+$salaryAdjustment) 1 20)
            }
        }
        $salaryAmount=[int]$salaryValue; $salarySource=[string]$salaryRow.coverage
        $salaryPrior=([double]$prior).ToString('0.00',[Globalization.CultureInfo]::InvariantCulture)
    }

    $record=[ordered]@{}
    foreach($property in $ability.PSObject.Properties){$record[$property.Name]=$property.Value}
    foreach($name in @('fielding_range','catching','throwing_power','throwing_accuracy','fielding_judgment','composure','leadership','aggressiveness','defense_source','defense_confidence','defense_ip','primary_defense_position','salary_10k_krw','salary_source','salary_prior_rating','salary_rating_adjustment','remaining_formula_version')){[void]$record.Remove($name)}
    $record['fielding_range']=$fieldingRange; $record['catching']=$catching
    $record['throwing_power']=$throwingPower; $record['throwing_accuracy']=$throwingAccuracy
    $record['fielding_judgment']=$fieldingJudgment; $record['composure']=$composure
    $record['leadership']=$leadership; $record['aggressiveness']=$aggressiveness
    $record['defense_source']=$defenseSource; $record['defense_confidence']=$defenseConfidence
    $record['defense_ip']=$defenseIp; $record['primary_defense_position']=$primaryPosition
    $record['salary_10k_krw']=$salaryAmount; $record['salary_source']=$salarySource
    $record['salary_prior_rating']=$salaryPrior; $record['salary_rating_adjustment']=$salaryAdjustment
    $record['remaining_formula_version']=$formulaVersion; $record['formula_version']=$formulaVersion
    [pscustomobject]$record
}

$futureColumns=@('fielding_range','catching','throwing_power','throwing_accuracy','fielding_judgment','composure','leadership','aggressiveness')
foreach($row in $output){foreach($column in $futureColumns){$value=[int]$row.$column;if($value-lt1-or$value-gt20){throw "Out of range: $($row.player_name) $column=$value"}}}
$output | Sort-Object snapshot_team, player_name, kbo_player_id | Export-Csv $AbilityPath -NoTypeInformation -Encoding UTF8
$levels=$output|Group-Object source_level|ForEach-Object{"$($_.Name)=$($_.Count)"}
$sources=$output|Group-Object defense_source|ForEach-Object{"$($_.Name)=$($_.Count)"}
$salaryMatched=@($output|Where-Object salary_source).Count
$salaryAdjusted=@($output|Where-Object {[int]$_.salary_rating_adjustment-ne0}).Count
Write-Output "COMPLETE hitters=$($output.Count) levels=$($levels -join ',') defense=$($sources -join ',') salary=$salaryMatched adjusted=$salaryAdjusted formula=$formulaVersion"
