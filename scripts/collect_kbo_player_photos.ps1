param(
    [string]$RosterPath = "data/source/kbo_2025_final_roster.csv",
    [string]$ManifestPath = "data/source/player_photo_manifest.csv",
    [string]$OutputDirectory = "image/players/local/originals",
    [int]$BatchSize = 10
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.Net.Http

$roster = @(Import-Csv -Encoding UTF8 -LiteralPath $RosterPath)
if ($roster.Count -ne 636) { throw "Expected 636 players, got $($roster.Count)" }
if (@($roster.kbo_player_id | Sort-Object -Unique).Count -ne 636) { throw "KBO player IDs must be unique" }

$manifest = @(Import-Csv -Encoding UTF8 -LiteralPath $ManifestPath)
$manifestById = @{}
foreach ($row in $manifest) { $manifestById[[string]$row.kbo_player_id] = $row }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate
$client = [System.Net.Http.HttpClient]::new($handler)
$client.Timeout = [TimeSpan]::FromSeconds(30)
$client.DefaultRequestHeaders.UserAgent.ParseAdd("KBOFM2025-LocalPlayerPhotoCollector/1.0")
$client.DefaultRequestHeaders.Referrer = [uri]"https://www.koreabaseball.com/"
$downloaded = 0
$missing = 0
$failed = 0

try {
    for ($start = 0; $start -lt $roster.Count; $start += $BatchSize) {
        $end = [Math]::Min($start + $BatchSize, $roster.Count)
        $pageRequests = [System.Collections.Generic.List[object]]::new()
        for ($index = $start; $index -lt $end; $index++) {
            $player = $roster[$index]
            $type = if ($player.position_group -eq "P") { "Pitcher" } else { "Hitter" }
            $pageUrl = "https://www.koreabaseball.com/Record/Player/${type}Detail/Basic.aspx?playerId=$($player.kbo_player_id)"
            $pageRequests.Add([pscustomobject]@{ Player = $player; PageUrl = $pageUrl; Task = $client.GetAsync($pageUrl) })
        }

        $imageRequests = [System.Collections.Generic.List[object]]::new()
        foreach ($request in $pageRequests) {
            $id = [string]$request.Player.kbo_player_id
            $manifestRow = $manifestById[$id]
            try {
                $response = $request.Task.Result
                $response.EnsureSuccessStatusCode() | Out-Null
                $html = $response.Content.ReadAsStringAsync().Result
                $match = [regex]::Match($html, '<img[^>]+id="[^"]*imgProgile"[^>]+src="([^"]+)"', [Text.RegularExpressions.RegexOptions]::IgnoreCase)
                if (-not $match.Success) { throw "Player profile image tag not found" }
                $imageUrl = [Net.WebUtility]::HtmlDecode($match.Groups[1].Value)
                if ($imageUrl.StartsWith("//")) { $imageUrl = "https:$imageUrl" }
                if ($imageUrl -match 'no-Image') {
                    $manifestRow.source_page_url = $request.PageUrl
                    $manifestRow.status = "official_photo_missing"
                    $manifestRow.notes = "KBO profile uses the no-image placeholder"
                    $missing++
                    continue
                }
                $imageRequests.Add([pscustomobject]@{ Player = $request.Player; PageUrl = $request.PageUrl; ImageUrl = $imageUrl; Task = $client.GetAsync($imageUrl) })
            }
            catch {
                $manifestRow.status = "page_failed"
                $manifestRow.notes = $_.Exception.Message
                $failed++
            }
        }

        foreach ($request in $imageRequests) {
            $id = [string]$request.Player.kbo_player_id
            $manifestRow = $manifestById[$id]
            try {
                $response = $request.Task.Result
                $response.EnsureSuccessStatusCode() | Out-Null
                $bytes = $response.Content.ReadAsByteArrayAsync().Result
                if ($bytes.Length -lt 1000 -or $bytes[0] -ne 0xFF -or $bytes[1] -ne 0xD8) { throw "Invalid KBO JPEG response" }
                $target = Join-Path $OutputDirectory "$id.jpg"
                [IO.File]::WriteAllBytes($target, $bytes)
                $manifestRow.source_page_url = $request.PageUrl
                $manifestRow.image_url = $request.ImageUrl
                $manifestRow.credit = "KBO official website"
                $manifestRow.license = "Official profile photo; redistribution rights unverified"
                $manifestRow.redistributable = "0"
                $manifestRow.approved = "0"
                $manifestRow.local_filename = "originals/$id.jpg"
                $manifestRow.status = "downloaded_local_only"
                $manifestRow.notes = "Local game-development copy; excluded from Git and redistribution packages"
                $downloaded++
            }
            catch {
                $manifestRow.status = "image_failed"
                $manifestRow.notes = $_.Exception.Message
                $failed++
            }
        }
        Write-Output "PROGRESS $end/$($roster.Count) downloaded=$downloaded missing=$missing failed=$failed"
    }
}
finally {
    $client.Dispose()
    $handler.Dispose()
    $manifest | Export-Csv -NoTypeInformation -Encoding UTF8 -LiteralPath $ManifestPath
}

Write-Output "COMPLETE total=$($roster.Count) downloaded=$downloaded missing=$missing failed=$failed"
