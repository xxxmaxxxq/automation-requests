param(
    [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
    [string[]]$ImagePath
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.IRandomAccessStreamWithContentType, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType = WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime] | Out-Null

function Await-WinRt($AsyncOperation, [Type]$ResultType) {
    $methods = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq "AsTask" -and
            $_.IsGenericMethod -and
            $_.GetParameters().Count -eq 1
        }

    $method = $methods | Select-Object -First 1
    $task = $method.MakeGenericMethod($ResultType).Invoke($null, @($AsyncOperation))
    $task.Wait()
    return $task.Result
}

function Get-OcrLines([string]$Path, [string]$LanguageTag) {
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $file = Await-WinRt ([Windows.Storage.StorageFile]::GetFileFromPathAsync($resolved)) ([Windows.Storage.StorageFile])
    $stream = Await-WinRt ($file.OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
    try {
        $decoder = Await-WinRt ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await-WinRt ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

        $language = [Windows.Globalization.Language]::new($LanguageTag)
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
        if (-not $engine) {
            $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
        }
        if (-not $engine) {
            throw "Windows OCR engine is not available"
        }

        $result = Await-WinRt ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        return @($result.Lines | ForEach-Object { $_.Text })
    }
    finally {
        if ($stream) {
            $stream.Dispose()
        }
    }
}

$resolvedImagePaths = foreach ($path in $ImagePath) {
    $path -split "," | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
}

$result = foreach ($path in $resolvedImagePaths) {
    try {
        $ruLines = @(Get-OcrLines $path "ru")
        $enLines = @(Get-OcrLines $path "en")
        [pscustomobject]@{
            Path = (Resolve-Path -LiteralPath $path).Path
            Lines = @($ruLines + $enLines | Select-Object -Unique)
            Error = $null
        }
    }
    catch {
        [pscustomobject]@{
            Path = $path
            Lines = @()
            Error = $_.Exception.Message
        }
    }
}

ConvertTo-Json -InputObject @($result) -Depth 5
