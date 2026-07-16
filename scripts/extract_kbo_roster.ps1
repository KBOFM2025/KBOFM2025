param(
    [string]$InputPath = "data/source/kbo_2025_registered_players.xlsx",
    [string]$OutputPath = "data/source/kbo_2025_opening_roster.csv"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Add-Type -AssemblyName System.IO.Compression.FileSystem

$teamNames = @{
    "KIA 타이거즈" = "KIA 타이거즈"
    "삼성 라이온즈" = "삼성 라이온즈"
    "LG 트윈스" = "LG 트윈스"
    "두산 베어스" = "두산 베어스"
    "KT 위즈" = "KT 위즈"
    "SSG 랜더스" = "SSG 랜더스"
    "롯데 자이언츠" = "롯데 자이언츠"
    "한화 이글스" = "한화 이글스"
    "NC 다이노스" = "NC 다이노스"
    "키움히어로즈" = "키움 히어로즈"
}

$positionCodes = @{
    "투수" = "P"
    "포수" = "C"
    "내야수" = "IF"
    "외야수" = "OF"
}

$expectedCounts = @{
    "KIA 타이거즈" = 61
    "삼성 라이온즈" = 62
    "LG 트윈스" = 61
    "두산 베어스" = 57
    "KT 위즈" = 60
    "SSG 랜더스" = 59
    "롯데 자이언츠" = 60
    "한화 이글스" = 57
    "NC 다이노스" = 59
    "키움 히어로즈" = 61
}

function Read-ZipXml {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [string]$EntryPath
    )

    $entry = $Archive.GetEntry($EntryPath)
    if ($null -eq $entry) {
        throw "XLSX entry not found: $EntryPath"
    }

    $reader = [System.IO.StreamReader]::new($entry.Open())
    try {
        return [xml]$reader.ReadToEnd()
    }
    finally {
        $reader.Dispose()
    }
}

function Get-CellValue {
    param(
        $Cell,
        [string[]]$SharedStrings
    )

    if ($null -eq $Cell) {
        return ""
    }

    $cellType = $Cell.GetAttribute("t")
    if ($cellType -eq "s") {
        return $SharedStrings[[int]$Cell.InnerText]
    }
    if ($cellType -eq "inlineStr") {
        return [string]$Cell.InnerText
    }
    return [string]$Cell.InnerText
}

$resolvedInput = (Resolve-Path $InputPath).Path
$archive = [System.IO.Compression.ZipFile]::OpenRead($resolvedInput)

try {
    $sharedStringsXml = Read-ZipXml -Archive $archive -EntryPath "xl/sharedStrings.xml"
    [string[]]$sharedStrings = @($sharedStringsXml.sst.si | ForEach-Object { $_.InnerText })
    $players = [System.Collections.Generic.List[object]]::new()

    foreach ($sheetNumber in 1..5) {
        $sheetXml = Read-ZipXml -Archive $archive -EntryPath "xl/worksheets/sheet$sheetNumber.xml"
        $rows = @{}

        foreach ($row in $sheetXml.SelectNodes("/*[local-name()='worksheet']/*[local-name()='sheetData']/*[local-name()='row']")) {
            $cells = @{}
            foreach ($cell in $row.SelectNodes("*[local-name()='c']")) {
                $column = ([regex]::Match($cell.GetAttribute("r"), "^[A-Z]+")).Value
                $cells[$column] = Get-CellValue -Cell $cell -SharedStrings $sharedStrings
            }
            $rows[[int]$row.GetAttribute("r")] = $cells
        }

        $teamStartRows = @(
            $rows.Keys |
                Where-Object { $rows[$_].ContainsKey("D") -and $teamNames.ContainsKey($rows[$_]["D"]) } |
                Sort-Object
        )

        for ($teamIndex = 0; $teamIndex -lt $teamStartRows.Count; $teamIndex++) {
            $startRow = $teamStartRows[$teamIndex]
            $endRow = if ($teamIndex + 1 -lt $teamStartRows.Count) {
                $teamStartRows[$teamIndex + 1] - 1
            }
            else {
                ($rows.Keys | Measure-Object -Maximum).Maximum
            }

            $teamName = $teamNames[$rows[$startRow]["D"]]
            $activePosition = ""

            # The KBO workbook fills each three-column block from top to bottom,
            # then continues the same category in the next block.
            foreach ($group in @(
                @{ Position = "A"; Name = "B"; Note = "C" },
                @{ Position = "D"; Name = "E"; Note = "F" },
                @{ Position = "G"; Name = "H"; Note = "I" }
            )) {
                for ($rowNumber = $startRow + 2; $rowNumber -le $endRow; $rowNumber++) {
                    if (-not $rows.ContainsKey($rowNumber)) {
                        continue
                    }

                    $cells = $rows[$rowNumber]
                    $positionText = if ($cells.ContainsKey($group.Position)) { $cells[$group.Position].Trim() } else { "" }
                    if ($positionText) {
                        $activePosition = $positionText
                    }

                    if (-not $positionCodes.ContainsKey($activePosition)) {
                        continue
                    }

                    $playerName = if ($cells.ContainsKey($group.Name)) { $cells[$group.Name].Trim() } else { "" }
                    if (-not $playerName) {
                        continue
                    }

                    $note = if ($cells.ContainsKey($group.Note)) { $cells[$group.Note].Trim() } else { "" }
                    $players.Add([pscustomobject]@{
                        snapshot_date = "2025-02-10"
                        team = $teamName
                        name = $playerName
                        position_group = $positionCodes[$activePosition]
                        position_name = $activePosition
                        is_rookie = [int]($note -eq "신인")
                        is_foreign = [int]($note -eq "외국인")
                        note = $note
                        source_sheet = $sheetNumber
                        source_cell = "$($group.Name)$rowNumber"
                        source = "https://www.koreabaseball.com/MediaNews/Notice/View.aspx?bdSe=11371"
                    })
                }
            }
        }
    }

    $duplicatePlayers = @($players | Group-Object team, name | Where-Object Count -gt 1)
    if ($duplicatePlayers.Count -gt 0) {
        Write-Warning "Same-name player rows preserved: $($duplicatePlayers.Name -join ', ')"
    }

    $countMismatches = [System.Collections.Generic.List[string]]::new()
    foreach ($teamName in $expectedCounts.Keys) {
        $actualCount = @($players | Where-Object team -eq $teamName).Count
        if ($actualCount -ne $expectedCounts[$teamName]) {
            $countMismatches.Add("${teamName}: expected $($expectedCounts[$teamName]), got $actualCount")
        }
    }
    if ($countMismatches.Count -gt 0 -or $players.Count -ne 597) {
        Write-Warning "Source/list count mismatch preserved for review: $($countMismatches -join '; '); total expected 597, got $($players.Count)"
    }

    $outputDirectory = Split-Path -Parent $OutputPath
    if ($outputDirectory) {
        New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
    }
    $players |
        Sort-Object team, position_group, name |
        Export-Csv -Path $OutputPath -NoTypeInformation -Encoding UTF8

    $players |
        Group-Object team |
        Sort-Object Name |
        Select-Object Name, Count
    Write-Output "TOTAL: $($players.Count)"
    Write-Output "OUTPUT: $((Resolve-Path $OutputPath).Path)"
}
finally {
    $archive.Dispose()
}
