param(
    [string]$RosterPath = "data/source/kbo_2025_roster_2025-10-31.csv",
    [string]$OutputPath = "data/source/kbo_2025_profile_candidates.csv",
    [int]$MaxNames = 0,
    [int]$BatchSize = 6
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Add-Type -AssemblyName System.Net.Http

$roster = @(Import-Csv -Encoding UTF8 $RosterPath)
$names = @($roster.name | Sort-Object -Unique)
if ($MaxNames -gt 0) { $names = @($names | Select-Object -First $MaxNames) }
$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate
$client = [System.Net.Http.HttpClient]::new($handler)
$client.BaseAddress = [uri]"https://www.koreabaseball.com"
$client.DefaultRequestHeaders.Referrer = [uri]"https://www.koreabaseball.com/Player/Search.aspx"
$client.DefaultRequestHeaders.Add("X-Requested-With", "XMLHttpRequest")
$client.Timeout = [timespan]::FromSeconds(30)

$candidates = [System.Collections.Generic.List[object]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

try {
    for ($batchStart = 0; $batchStart -lt $names.Count; $batchStart += $BatchSize) {
        $pending = [System.Collections.Generic.List[object]]::new()
        $batchEnd = [Math]::Min($batchStart + $BatchSize, $names.Count)
        for ($index = $batchStart; $index -lt $batchEnd; $index++) {
            $name = $names[$index]
            $fields = [System.Collections.Generic.Dictionary[string,string]]::new()
            $fields.Add("name", $name)
            $form = [System.Net.Http.FormUrlEncodedContent]::new($fields)
            $pending.Add([pscustomobject]@{
                Name = $name
                Form = $form
                Task = $client.PostAsync("/ws/Controls.asmx/GetSearchPlayer", $form)
            })
        }

        foreach ($request in $pending) {
            $json = $null
            try {
                $response = $request.Task.Result
                $response.EnsureSuccessStatusCode() | Out-Null
                $body = $response.Content.ReadAsStringAsync().Result.TrimStart([char]0xFEFF)
                $json = $body | ConvertFrom-Json
            }
            catch {
                $errors.Add("$($request.Name): $($_.Exception.Message)")
            }
            finally {
                $request.Form.Dispose()
            }

            if ($null -ne $json) {
                foreach ($bucket in @("now", "retire")) {
                    foreach ($candidate in @($json.$bucket)) {
                        if ($null -eq $candidate -or $candidate.P_NM -ne $request.Name) { continue }
                        $candidates.Add([pscustomobject]@{
                            search_name = $request.Name
                            candidate_status = $bucket
                            kbo_player_id = [string]$candidate.P_ID
                            name = $candidate.P_NM
                            team_id = $candidate.T_ID
                            team_name = $candidate.T_NM
                            position_name = $candidate.POS_NO
                            bats_throws = $candidate.P_TYPE
                            profile_link = $candidate.P_LINK
                            source_url = "https://www.koreabaseball.com/ws/Controls.asmx/GetSearchPlayer"
                        })
                    }
                }
            }
        }

        if ($batchEnd % 48 -eq 0 -or $batchEnd -eq $names.Count) {
            Write-Output "SEARCHED=$batchEnd/$($names.Count) CANDIDATES=$($candidates.Count) ERRORS=$($errors.Count)"
        }
        Start-Sleep -Milliseconds 25
    }
}
finally {
    $client.Dispose()
    $handler.Dispose()
}

if ($errors.Count -gt 0) {
    throw "Profile search failures: $($errors -join '; ')"
}

$candidates |
    Sort-Object search_name, candidate_status, team_name, position_name, kbo_player_id |
    Export-Csv -Path $OutputPath -NoTypeInformation -Encoding UTF8

Write-Output "NAMES=$($names.Count) CANDIDATES=$($candidates.Count) OUTPUT=$((Resolve-Path $OutputPath).Path)"
