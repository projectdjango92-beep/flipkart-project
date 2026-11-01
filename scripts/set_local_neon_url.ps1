<#
Stores a Neon DATABASE_URL in the ignored local .env file without echoing it.
Run from the project directory: .\scripts\set_local_neon_url.ps1
#>

$envFile = Join-Path $PSScriptRoot "..\\.env"
$secureUrl = Read-Host "Paste the Neon pooled DATABASE_URL (input is hidden)" -AsSecureString
$plainUrlPointer = [IntPtr]::Zero

try {
    $plainUrlPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureUrl)
    $databaseUrl = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($plainUrlPointer)

    if (-not $databaseUrl.StartsWith("postgresql://") -and -not $databaseUrl.StartsWith("postgres://")) {
        throw "The value does not look like a PostgreSQL connection URL. Nothing was saved."
    }

    $existingLines = if (Test-Path $envFile) { Get-Content -LiteralPath $envFile } else { @() }
    $newLines = @($existingLines | Where-Object { $_ -notmatch '^\s*DATABASE_URL\s*=' })
    $newLines += "DATABASE_URL=$databaseUrl"
    Set-Content -LiteralPath $envFile -Value $newLines -Encoding utf8
    Write-Host "DATABASE_URL saved to the ignored local .env file. The value was not displayed."
}
finally {
    if ($plainUrlPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($plainUrlPointer)
    }
    Remove-Variable databaseUrl -ErrorAction SilentlyContinue
}
