param(
    [string]$OutputPath = "data/source/kbo_2025_pitch_tracking.csv"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# KBO Talent publishes these values through a browser-readable Supabase view.
# The anon key is intentionally public and is the same key shipped in the site bundle.
$endpoint = "https://lrkzhxjgnhipsamizmys.supabase.co/rest/v1/pitching_metrics_v2_leaderboard?select=*&season=eq.2025&game_type=eq.REGULAR&order=n_pitches.desc"
$anonKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxya3poeGpnbmhpcHNhbWl6bXlzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1ODEyODQsImV4cCI6MjA5MDE1NzI4NH0.YB44wQBunRpJ8R853zIN2MggsAOykJmvZXCWMJtfqVQ"
$headers = @{ apikey = $anonKey; Authorization = "Bearer $anonKey" }
$response = Invoke-RestMethod -Uri $endpoint -Headers $headers -Method Get -TimeoutSec 60
$rows = @($response.GetEnumerator())
if ($rows.Count -eq 0) { throw "No 2025 KBO pitch tracking rows returned." }

function Get-PropertyValue {
    param([object]$Object, [string]$Name, [object]$Default = $null)
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property -or $null -eq $property.Value) { return $Default }
    return $property.Value
}

$pitchNames = [ordered]@{
    FF = "Four-seam"; SI = "Sinker"; FC = "Cutter"; CH = "Changeup"; SL = "Slider"
    CU = "Curve"; FS = "Splitter"; ST = "Sweeper"; KN = "Knuckleball"
}
$output = @(foreach ($row in $rows) {
    $record = [ordered]@{
        season = 2025
        kbo_player_id = [string]$row.pitcher_pcode
        n_pitches = $row.n_pitches
        avg_speed = $row.avg_speed
        k_stuff_plus = $row.k_stuff_v2
        k_location_plus = $row.k_control_v2
        k_rate = $row.k_rate
        bb_rate = $row.bb_rate
        whiff_rate = $row.whiff_rate
        csw_rate = $row.csw_rate
        repertoire = ""
        pitch_detail_json = ""
        source_url = "https://www.kbostuff.app/stuff/$($row.pitcher_pcode)?season=2025"
    }
    $details = $row.pitch_type_details
    $used = [System.Collections.Generic.List[object]]::new()
    if ($null -ne $details) {
        foreach ($property in $details.PSObject.Properties) {
            $code = $property.Name
            $value = $property.Value
            $usage = [double](Get-PropertyValue $value "usage_pct" 0.0)
            $used.Add([pscustomobject]@{
                code = $code
                name = if ($pitchNames.Contains($code)) { $pitchNames[$code] } else { $code }
                n = [int](Get-PropertyValue $value "n" 0)
                usage_pct = $usage
                speed = (Get-PropertyValue $value "speed")
                k_stuff_plus = (Get-PropertyValue $value "k_stuff_v2" (Get-PropertyValue $value "k_stuff"))
                k_location_plus = (Get-PropertyValue $value "k_control" (Get-PropertyValue $value "k_location"))
                whiff_rate = (Get-PropertyValue $value "whiff")
                csw_rate = (Get-PropertyValue $value "csw")
            })
        }
    }
    $sorted = @($used | Sort-Object usage_pct -Descending)
    $record.repertoire = (($sorted | Where-Object usage_pct -ge 0.03 | ForEach-Object { $_.name }) -join "/")
    $record.pitch_detail_json = if ($sorted.Count) { $sorted | ConvertTo-Json -Compress -Depth 4 } else { "[]" }
    [pscustomobject]$record
})

$output | Sort-Object kbo_player_id | Export-Csv $OutputPath -NoTypeInformation -Encoding UTF8
Write-Output "COMPLETE tracking_rows=$($output.Count) output=$OutputPath"
