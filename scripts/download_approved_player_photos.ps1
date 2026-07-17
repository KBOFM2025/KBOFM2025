param(
    [string]$ManifestPath = "data/source/player_photo_manifest.csv",
    [string]$OutputDirectory = "image/players/local",
    [int]$DelayMilliseconds = 1200,
    [int]$MaximumMegabytes = 10
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.Net.Http

if (-not (Test-Path -LiteralPath $ManifestPath)) {
    throw "Photo manifest not found: $ManifestPath"
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$extensionByContentType = @{
    "image/jpeg" = ".jpg"
    "image/png" = ".png"
    "image/webp" = ".webp"
}

function Test-ImageSignature {
    param([byte[]]$Bytes, [string]$ContentType)
    if ($ContentType -eq "image/jpeg") {
        return $Bytes.Length -ge 3 -and $Bytes[0] -eq 0xFF -and $Bytes[1] -eq 0xD8 -and $Bytes[2] -eq 0xFF
    }
    if ($ContentType -eq "image/png") {
        return $Bytes.Length -ge 8 -and $Bytes[0] -eq 0x89 -and $Bytes[1] -eq 0x50 -and $Bytes[2] -eq 0x4E -and $Bytes[3] -eq 0x47
    }
    if ($ContentType -eq "image/webp") {
        return $Bytes.Length -ge 12 -and
            [Text.Encoding]::ASCII.GetString($Bytes, 0, 4) -eq "RIFF" -and
            [Text.Encoding]::ASCII.GetString($Bytes, 8, 4) -eq "WEBP"
    }
    return $false
}

$rows = @(Import-Csv -Encoding UTF8 -LiteralPath $ManifestPath)
$approvedRows = @($rows | Where-Object {
    $_.approved -in @("1", "true", "TRUE", "yes", "YES") -and $_.image_url
})

$seenIds = @{}
$downloaded = 0
$skipped = 0
$failed = 0
$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AllowAutoRedirect = $true
$client = [System.Net.Http.HttpClient]::new($handler)
$client.Timeout = [TimeSpan]::FromSeconds(30)
$client.DefaultRequestHeaders.UserAgent.ParseAdd("KBOManager2025-LocalPhotoImporter/1.0")

try {
    foreach ($row in $approvedRows) {
        $id = [string]$row.kbo_player_id
        if ($id -notmatch '^\d{5,8}$') {
            Write-Warning "SKIP invalid KBO player ID: $id"
            $row.status = "invalid_id"
            $skipped++
            continue
        }
        if ($seenIds.ContainsKey($id)) {
            Write-Warning "SKIP duplicate KBO player ID: $id"
            $row.status = "duplicate_id"
            $skipped++
            continue
        }
        $seenIds[$id] = $true

        $uri = $null
        if (-not [Uri]::TryCreate($row.image_url, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -ne "https") {
            Write-Warning "SKIP non-HTTPS image URL for $id"
            $row.status = "invalid_url"
            $skipped++
            continue
        }
        if ($uri.Host -in @("localhost", "127.0.0.1", "::1")) {
            Write-Warning "SKIP local image URL for $id"
            $row.status = "local_url_blocked"
            $skipped++
            continue
        }

        try {
            $response = $client.GetAsync($uri).GetAwaiter().GetResult()
            $response.EnsureSuccessStatusCode() | Out-Null
            $contentType = [string]$response.Content.Headers.ContentType.MediaType
            if (-not $extensionByContentType.ContainsKey($contentType)) {
                throw "Unsupported content type: $contentType"
            }
            $bytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
            if ($bytes.Length -gt $MaximumMegabytes * 1MB) {
                throw "Image exceeds ${MaximumMegabytes}MB"
            }
            if (-not (Test-ImageSignature $bytes $contentType)) {
                throw "File signature does not match $contentType"
            }

            $extension = $extensionByContentType[$contentType]
            $target = Join-Path $OutputDirectory "$id$extension"
            [IO.File]::WriteAllBytes($target, $bytes)
            $row.local_filename = Split-Path -Leaf $target
            $row.status = "downloaded"
            Write-Output "DOWNLOADED id=$id name=$($row.player_name) file=$target"
            $downloaded++
        }
        catch {
            $row.status = "failed"
            Write-Warning "FAILED id=$id url=$($row.image_url) error=$($_.Exception.Message)"
            $failed++
        }
        Start-Sleep -Milliseconds $DelayMilliseconds
    }
}
finally {
    $client.Dispose()
    $handler.Dispose()
}

$rows | Export-Csv -NoTypeInformation -Encoding UTF8 -LiteralPath $ManifestPath
Write-Output "COMPLETE approved=$($approvedRows.Count) downloaded=$downloaded skipped=$skipped failed=$failed"
