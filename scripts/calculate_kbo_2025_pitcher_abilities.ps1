param(
    [string]$RosterPath = "data/source/kbo_2025_final_roster.csv",
    [string]$FirstTeamPath = "data/source/kbo_2025_first_team_pitching.csv",
    [string]$FuturesPath = "data/source/kbo_2025_futures_pitching.csv",
    [string]$TrackingPath = "data/source/kbo_2025_pitch_tracking.csv",
    [string]$SalaryPath = "data/source/kbo_2025_verified_pitcher_salaries.csv",
    [string]$OutputPath = "data/source/kbo_2025_pitcher_abilities.csv"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$culture = [Globalization.CultureInfo]::InvariantCulture
$formulaVersion = "kbo-pitcher-abilities-v1-official-tracking-regressed"
$pitchColumns = [ordered]@{ FF="pitch_four_seam"; SI="pitch_sinker"; FC="pitch_cutter"; CH="pitch_changeup"; SL="pitch_slider"; CU="pitch_curve"; FS="pitch_splitter"; ST="pitch_sweeper"; KN="pitch_knuckleball" }

function Number([object]$Value, [double]$Default=0.0) {
    $parsed = 0.0
    if ([double]::TryParse([string]$Value, [Globalization.NumberStyles]::Any, $culture, [ref]$parsed)) { return $parsed }
    return $Default
}
function Clamp([double]$Value, [double]$Min, [double]$Max) { return [Math]::Max($Min,[Math]::Min($Max,$Value)) }
function Percentile([object[]]$Values, [double]$Value) {
    if ($Values.Count -eq 0) { return 0.5 }
    $less=0; $equal=0
    foreach($candidate in $Values){ if([double]$candidate -lt $Value){$less++} elseif([Math]::Abs([double]$candidate-$Value)-lt 0.0000001){$equal++} }
    return ($less + 0.5*$equal) / $Values.Count
}
function Rating([double]$Percentile, [int]$Adjustment=0) {
    $value = [int][Math]::Round(1 + 19 * [Math]::Pow((Clamp $Percentile 0 1), 0.92)) + $Adjustment
    return [int](Clamp $value 1 20)
}
function PlusRating([double]$Plus, [double]$Reliability=1.0) {
    $regressed = 100 + ($Plus-100) * (Clamp $Reliability 0 1)
    return [int](Clamp ([Math]::Round(10 + ($regressed-100)/4.5)) 1 20)
}
function ReadMap([string]$Path) {
    $map=@{}
    foreach($row in @(Import-Csv -Encoding UTF8 $Path)){ $map[[string]$row.kbo_player_id]=$row }
    return $map
}

$roster=@(Import-Csv -Encoding UTF8 $RosterPath | Where-Object position_group -eq "P")
if($roster.Count -ne 319){throw "Expected 319 pitchers, got $($roster.Count)"}
$first=ReadMap $FirstTeamPath; $futures=ReadMap $FuturesPath; $tracking=ReadMap $TrackingPath; $salary=ReadMap $SalaryPath
$models=[System.Collections.Generic.List[object]]::new()

foreach($player in $roster){
    $id=[string]$player.kbo_player_id; $row=$null; $source="NONE"; $leagueAdjustment=0; $prior=300.0
    if($first.ContainsKey($id) -and $first[$id].has_record -eq "1" -and (Number $first[$id].TBF) -gt 0){$row=$first[$id];$source="KBO";$prior=140.0}
    elseif($futures.ContainsKey($id) -and $futures[$id].has_record -eq "1" -and (Number $futures[$id].TBF) -gt 0){$row=$futures[$id];$source="FUTURES";$leagueAdjustment=-2;$prior=260.0}
    $tbf=if($null-ne$row){Number $row.TBF}else{0}; $outs=if($null-ne$row){Number $row.IP_OUTS}else{0}; $ip=$outs/3.0
    $g=if($null-ne$row){Number $row.G}else{0}; $so=if($null-ne$row){Number $row.SO}else{0}; $bb=if($null-ne$row){Number $row.BB}else{0}; $hbp=if($null-ne$row){Number $row.HBP}else{0}; $hr=if($null-ne$row){Number $row.HR}else{0}
    $era=if($null-ne$row){Number $row.ERA 4.50}else{4.50}; $whip=if($null-ne$row){Number $row.WHIP 1.45}else{1.45}
    $kRate=if($tbf-gt 0){$so/$tbf}else{0.18}; $bbRate=if($tbf-gt 0){$bb/$tbf}else{0.09}; $hrRate=if($tbf-gt 0){$hr/$tbf}else{0.025}
    $rawFip=if($ip-gt 0){(13*$hr+3*($bb+$hbp)-2*$so)/$ip}else{0}
    $models.Add([pscustomobject]@{Player=$player;Id=$id;Row=$row;Source=$source;Adjustment=$leagueAdjustment;Prior=$prior;TBF=$tbf;IP=$ip;G=$g;ERA=$era;WHIP=$whip;KRate=$kRate;BBRate=$bbRate;HRRate=$hrRate;RawFIP=$rawFip})
}

foreach($level in @("KBO","FUTURES")){
    $group=@($models|Where-Object Source -eq $level)
    if($group.Count-eq0){continue}
    $totalTbf=($group|Measure-Object TBF -Sum).Sum; $totalIp=($group|Measure-Object IP -Sum).Sum
    $meanK=($group|ForEach-Object {$_.KRate*$_.TBF}|Measure-Object -Sum).Sum/$totalTbf
    $meanBB=($group|ForEach-Object {$_.BBRate*$_.TBF}|Measure-Object -Sum).Sum/$totalTbf
    $meanHR=($group|ForEach-Object {$_.HRRate*$_.TBF}|Measure-Object -Sum).Sum/$totalTbf
    $meanWhip=($group|ForEach-Object {$_.WHIP*$_.IP}|Measure-Object -Sum).Sum/$totalIp
    $meanEra=($group|ForEach-Object {$_.ERA*$_.IP}|Measure-Object -Sum).Sum/$totalIp
    $meanRawFip=($group|ForEach-Object {$_.RawFIP*$_.IP}|Measure-Object -Sum).Sum/$totalIp
    $fipConstant=$meanEra-$meanRawFip
    foreach($m in $group){
        $weight=$m.TBF/($m.TBF+$m.Prior)
        $m|Add-Member AdjK ($meanK+($m.KRate-$meanK)*$weight)
        $m|Add-Member AdjBB ($meanBB+($m.BBRate-$meanBB)*$weight)
        $m|Add-Member AdjHR ($meanHR+($m.HRRate-$meanHR)*$weight)
        $m|Add-Member AdjWHIP ($meanWhip+($m.WHIP-$meanWhip)*$weight)
        $m|Add-Member AdjERA ($meanEra+($m.ERA-$meanEra)*$weight)
        $m|Add-Member FIP ($m.RawFIP+$fipConstant)
        $m|Add-Member AdjFIP (($meanRawFip+($m.RawFIP-$meanRawFip)*$weight)+$fipConstant)
    }
}

$output=[System.Collections.Generic.List[object]]::new()
foreach($m in $models){
    $group=@($models|Where-Object Source -eq $m.Source)
    $ratings=[ordered]@{}
    if($m.Source-eq"NONE"){
        foreach($key in @("pitcher_velocity","pitcher_stuff","pitcher_command","pitcher_movement","pitcher_stamina","pitcher_pitchability","pitcher_strikeout","pitcher_walk_control","pitcher_composure")){$ratings[$key]=8}
    }else{
        $kP=Percentile @($group.AdjK) $m.AdjK; $bbP=1-(Percentile @($group.AdjBB) $m.AdjBB); $hrP=1-(Percentile @($group.AdjHR) $m.AdjHR)
        $whipP=1-(Percentile @($group.AdjWHIP) $m.AdjWHIP); $eraP=1-(Percentile @($group.AdjERA) $m.AdjERA); $fipP=1-(Percentile @($group.AdjFIP) $m.AdjFIP)
        $track=if($tracking.ContainsKey($m.Id)){$tracking[$m.Id]}else{$null}; $trackReliability=if($null-ne$track){(Number $track.n_pitches)/((Number $track.n_pitches)+450)}else{0}
        $stuffP=0.45*$kP+0.30*$fipP+0.25*$hrP; $commandP=0.55*$bbP+0.30*$whipP+0.15*$fipP
        $movementP=0.55*$hrP+0.25*$whipP+0.20*$kP
        if($null-ne$track){
            $stuffTrack=(PlusRating (Number $track.k_stuff_plus 100) $trackReliability); $locTrack=(PlusRating (Number $track.k_location_plus 100) $trackReliability)
            $stuff=[Math]::Round(0.55*(Rating $stuffP $m.Adjustment)+0.45*$stuffTrack)
            $command=[Math]::Round(0.55*(Rating $commandP $m.Adjustment)+0.45*$locTrack)
            $velocity=[int](Clamp ([Math]::Round(10+((Number $track.avg_speed 143)-143)/1.7)) 1 20)
        }else{$stuff=Rating $stuffP $m.Adjustment;$command=Rating $commandP $m.Adjustment;$velocity=8}
        $ipPerGame=if($m.G-gt0){$m.IP/$m.G}else{0}; $stamina=[int](Clamp ([Math]::Round(7+$ipPerGame*1.9+[Math]::Min(3,$m.IP/55))+$m.Adjustment) 1 20)
        $ratings.pitcher_velocity=$velocity; $ratings.pitcher_stuff=[int](Clamp $stuff 1 20); $ratings.pitcher_command=[int](Clamp $command 1 20)
        $ratings.pitcher_movement=Rating $movementP $m.Adjustment; $ratings.pitcher_stamina=$stamina
        $ratings.pitcher_pitchability=Rating (0.30*$kP+0.25*$bbP+0.25*$fipP+0.20*$whipP) $m.Adjustment
        $ratings.pitcher_strikeout=Rating $kP $m.Adjustment; $ratings.pitcher_walk_control=Rating $bbP $m.Adjustment
        $ratings.pitcher_composure=Rating (0.45*$eraP+0.35*$whipP+0.20*$fipP) $m.Adjustment
    }
    $salaryAdjustment=0; $salaryValue=""
    if($salary.ContainsKey($m.Id)){
        $salaryValue=[int](Number $salary[$m.Id].salary_10k_krw); $composite=($ratings.pitcher_pitchability+$ratings.pitcher_composure)/2.0
        $priorRating=10+[Math]::Log($salaryValue/16071.0,2)*1.2
        if($priorRating-$composite-ge2){$salaryAdjustment=1;$ratings.pitcher_pitchability=[int](Clamp ($ratings.pitcher_pitchability+1) 1 20);$ratings.pitcher_composure=[int](Clamp ($ratings.pitcher_composure+1) 1 20)}
    }
    $pitchRatings=[ordered]@{};foreach($column in $pitchColumns.Values){$pitchRatings[$column]=""}
    $repertoire="";$rawTrack=$null
    if($tracking.ContainsKey($m.Id)){
        $rawTrack=$tracking[$m.Id];$repertoire=$rawTrack.repertoire
        $parsedPitches = $rawTrack.pitch_detail_json | ConvertFrom-Json
        foreach($pitch in @($parsedPitches.GetEnumerator())){
            if(-not $pitchColumns.Contains([string]$pitch.code)){continue};$n=Number $pitch.n;if($n-lt10){continue}
            $plus=0.65*(Number $pitch.k_stuff_plus 100)+0.35*(Number $pitch.k_location_plus 100);$rel=$n/($n+90)
            $pitchRatings[$pitchColumns[[string]$pitch.code]]=PlusRating $plus $rel
        }
    }
    $confidence=if($m.Source-eq"KBO" -and $m.TBF-ge300){"high"}elseif($m.Source-ne"NONE" -and $m.TBF-ge100){"medium"}elseif($m.Source-ne"NONE"){"low"}else{"none"}
    $record=[ordered]@{season=2025;kbo_player_id=$m.Id;player_uid=$m.Player.player_uid;team=$m.Player.team;player_name=$m.Player.name;source_level=$m.Source;sample_tbf=[int]$m.TBF;sample_ip=$m.IP.ToString("0.0",$culture);confidence=$confidence;repertoire=$repertoire}
    foreach($key in $ratings.Keys){$record[$key]=$ratings[$key]};foreach($key in $pitchRatings.Keys){$record[$key]=$pitchRatings[$key]}
    $record.avg_velocity=if($null-ne$rawTrack){(Number $rawTrack.avg_speed).ToString("0.0",$culture)}else{""};$record.k_stuff_plus=if($null-ne$rawTrack){(Number $rawTrack.k_stuff_plus).ToString("0.0",$culture)}else{""};$record.k_location_plus=if($null-ne$rawTrack){(Number $rawTrack.k_location_plus).ToString("0.0",$culture)}else{""};$record.whiff_rate=if($null-ne$rawTrack){(Number $rawTrack.whiff_rate).ToString("0.000",$culture)}else{""};$record.csw_rate=if($null-ne$rawTrack){(Number $rawTrack.csw_rate).ToString("0.000",$culture)}else{""};$record.k_rate=if($m.Source-ne"NONE"){$m.KRate.ToString("0.000",$culture)}else{""};$record.bb_rate=if($m.Source-ne"NONE"){$m.BBRate.ToString("0.000",$culture)}else{""};$record.hr_rate=if($m.Source-ne"NONE"){$m.HRRate.ToString("0.000",$culture)}else{""};$record.fip=if($m.Source-ne"NONE"){$m.FIP.ToString("0.00",$culture)}else{""};$record.pitch_detail_json=if($null-ne$rawTrack){$rawTrack.pitch_detail_json}else{"[]"};$record.salary_10k_krw=$salaryValue;$record.salary_rating_adjustment=$salaryAdjustment;$record.formula_version=$formulaVersion;$record.kbo_source_url=if($null-ne$m.Row){$m.Row.source_url}else{""};$record.tracking_source_url=if($null-ne$rawTrack){$rawTrack.source_url}else{""}
    $output.Add([pscustomobject]$record)
}

$output|Sort-Object team,player_name,kbo_player_id|Export-Csv $OutputPath -NoTypeInformation -Encoding UTF8
Write-Output "COMPLETE pitchers=$($output.Count) KBO=$(@($output|Where-Object source_level -eq KBO).Count) FUTURES=$(@($output|Where-Object source_level -eq FUTURES).Count) NONE=$(@($output|Where-Object source_level -eq NONE).Count) formula=$formulaVersion"
