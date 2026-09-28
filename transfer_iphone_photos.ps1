param(
    [string]$Subject = "",

    [int]$Count = 0,

    [string]$DesktopRootName = "РєРѕР¶СѓС…РѕРІ",

    [string]$TargetRootPath = "",

    [string]$TargetPath = "",

    [string]$MonthFolderName = "",

    [switch]$Move
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Get-DesktopPath {
    $desktop = [Environment]::GetFolderPath("Desktop")
    if (-not [string]::IsNullOrWhiteSpace($desktop) -and (Test-Path -LiteralPath $desktop)) {
        return $desktop
    }

    $registryDesktop = (Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders").Desktop
    if (-not [string]::IsNullOrWhiteSpace($registryDesktop)) {
        $expanded = [Environment]::ExpandEnvironmentVariables($registryDesktop)
        if (Test-Path -LiteralPath $expanded) {
            return $expanded
        }
        return $expanded
    }

    throw "Desktop path not found"
}

function Get-SafeFolderName([string]$Name) {
    $invalid = [System.IO.Path]::GetInvalidFileNameChars()
    $safe = $Name
    foreach ($char in $invalid) {
        $safe = $safe.Replace($char, "_")
    }
    return ($safe -replace "\s+", " ").Trim()
}

function Get-OrCreate-MonthFolder([string]$RootPath) {
    $now = Get-Date
    if (-not [string]::IsNullOrWhiteSpace($MonthFolderName)) {
        $monthPath = Join-Path $RootPath $MonthFolderName
        New-Item -ItemType Directory -Force -Path $monthPath | Out-Null
        return $monthPath
    }

    $variants = @(
        $now.ToString("MM.yy"),
        $now.ToString("yyyy.MM"),
        $now.ToString("yyyyMM"),
        $now.ToString("MM"),
        [int]$now.Month,
        "РјР°Р№",
        "РњР°Р№"
    ) | ForEach-Object { [string]$_ }

    $existing = Get-ChildItem -LiteralPath $RootPath -Directory -ErrorAction SilentlyContinue |
        Where-Object {
            $folderName = $_.Name
            $variants | Where-Object { $folderName -like "*$_*" }
        } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($existing) {
        return $existing.FullName
    }

    $monthPath = Join-Path $RootPath $now.ToString("yyyy.MM")
    New-Item -ItemType Directory -Force -Path $monthPath | Out-Null
    return $monthPath
}

function Wait-ForCopiedFiles([string]$TargetPath, [int]$ExpectedCount) {
    for ($i = 0; $i -lt 30; $i++) {
        $files = Get-ChildItem -LiteralPath $TargetPath -File -ErrorAction SilentlyContinue
        if ($files.Count -ge $ExpectedCount) {
            return
        }
        Start-Sleep -Milliseconds 500
    }

    throw "Files were not copied in time: $TargetPath"
}

if (-not [string]::IsNullOrWhiteSpace($TargetPath)) {
    New-Item -ItemType Directory -Force -Path $TargetPath | Out-Null
    $targetPath = (Resolve-Path -LiteralPath $TargetPath).Path
} else {
    if ([string]::IsNullOrWhiteSpace($Subject)) {
        throw "Subject is required when TargetPath is not specified"
    }

    $safeSubject = Get-SafeFolderName $Subject
    if ([string]::IsNullOrWhiteSpace($TargetRootPath)) {
        $desktop = Get-DesktopPath
        $rootPath = Join-Path $desktop $DesktopRootName
    } else {
        $rootPath = $TargetRootPath
    }
    New-Item -ItemType Directory -Force -Path $rootPath | Out-Null

    $monthPath = Get-OrCreate-MonthFolder $rootPath
    $targetPath = Join-Path $monthPath $safeSubject
    New-Item -ItemType Directory -Force -Path $targetPath | Out-Null
}

$shell = New-Object -ComObject Shell.Application
$computer = $shell.Namespace(17)

$iphone = $computer.Items() |
    Where-Object { $_.Name -like "*iPhone*" -or $_.Name -like "*Apphone*" } |
    Select-Object -First 1

if (-not $iphone) {
    throw "Apple iPhone / Apphone not found in This PC"
}

$storage = $iphone.GetFolder.Items() |
    Where-Object { $_.Name -eq "Internal Storage" } |
    Select-Object -First 1

if (-not $storage) {
    throw "Internal Storage not found on iPhone"
}

$phoneFolders = $storage.GetFolder.Items() |
    Where-Object { $_.Name -match "^\d{6}(_.*)?$" } |
    Sort-Object @{
        Expression = {
            if ($_.Name -match "^(\d{6})(?:_(.*))?$") {
                $suffix = if ($matches[2]) { $matches[2] } else { "" }
                "{0}_{1}" -f $matches[1], $suffix
            } else {
                $_.Name
            }
        }
    } -Descending |
    Select-Object

if (-not $phoneFolders) {
    throw "No iPhone photo month folder found"
}

$phoneMonth = $null

$photos = @()
foreach ($folder in $phoneFolders) {
    $folderPhotos = @(
        $folder.GetFolder.Items() |
            Where-Object { $_.Name -match "\.(jpg|jpeg|png|heic)$" -or $_.Type -match "JPEG|PNG|HEIC|Рисунок" } |
            Sort-Object Name
    )
    Write-Host "Check iPhone folder: $($folder.Name) ($($folderPhotos.Count) photo files)"
    if (($Count -le 0 -and $folderPhotos.Count -gt 0) -or ($Count -gt 0 -and $folderPhotos.Count -ge $Count)) {
        $phoneMonth = $folder
        if ($Count -le 0) {
            $photos = @($folderPhotos)
        } else {
            $photos = @($folderPhotos | Select-Object -Last $Count | Sort-Object Name)
        }
        break
    }
}

if (-not $phoneMonth) {
    if ($Count -le 0) {
        throw "No iPhone photo folder has photos"
    }
    throw "No iPhone photo folder has enough photos: need $Count"
}

$phoneMonthName = $phoneMonth.Name
Write-Host "Use iPhone folder: $phoneMonthName"

if ($Count -gt 0 -and $photos.Count -lt $Count) {
    throw "Not enough photos in ${phoneMonthName}: found $($photos.Count), need $Count"
}

$destination = $shell.Namespace($targetPath)
foreach ($photo in $photos) {
    Write-Host "Copy $($photo.Name) -> $targetPath"
    $destination.CopyHere($photo, 16)
}

Wait-ForCopiedFiles $targetPath $photos.Count

if ($Move) {
    foreach ($photo in $photos) {
        Write-Host "Delete from phone $($photo.Name)"
        $photo.InvokeVerb("delete")
        Start-Sleep -Milliseconds 500
    }
}

Write-Host ""
Write-Host "Done:"
Write-Host $targetPath
