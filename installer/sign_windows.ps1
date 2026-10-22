<#
.SYNOPSIS
    Helper script to generate a code-signing certificate or sign LOKI Windows binaries/installers.

.DESCRIPTION
    1. Generate a self-signed Code Signing certificate (.pfx + .cer + Base64 for GitHub Secrets):
       .\installer\sign_windows.ps1 -GenerateCert -Publisher "Elabsurdo984" -Password "YourStrongPassword"

    2. Sign an executable or installer using a .pfx file:
       .\installer\sign_windows.ps1 -FilePath "dist\loki-setup-windows-amd64.exe" -PfxPath "loki-cert.pfx" -Password "YourStrongPassword"
#>

param(
    [switch]$GenerateCert,
    [string]$Publisher = "Elabsurdo984",
    [string]$Password = "loki-dev-cert",
    [string]$PfxPath = "loki-codesign.pfx",
    [string]$CerPath = "loki-codesign.cer",
    [string]$FilePath = ""
)

$ErrorActionPreference = "Stop"

if ($GenerateCert) {
    Write-Host "Generating self-signed Code Signing certificate for CN=$Publisher..." -ForegroundColor Cyan
    $cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject "CN=$Publisher" `
        -KeyAlgorithm RSA `
        -KeyLength 2048 `
        -Provider "Microsoft Enhanced RSA and AES Cryptographic Provider" `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -NotAfter (Get-Date).AddYears(3)

    $securePwd = ConvertTo-SecureString -String $Password -Force -AsPlainText
    Export-PfxCertificate -Cert $cert -FilePath $PfxPath -Password $securePwd | Out-Null
    Export-Certificate -Cert $cert -FilePath $CerPath | Out-Null

    $base64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path $PfxPath)))
    $base64File = "$PfxPath.base64.txt"
    Set-Content -Path $base64File -Value $base64 -NoNewline

    Write-Host "`n✔ Certificate generated successfully!" -ForegroundColor Green
    Write-Host "  • Private PFX (keep secret, gitignored): $PfxPath"
    Write-Host "  • Public CER (install to Trusted Root / Trusted Publishers): $CerPath"
    Write-Host "  • Base64 for GitHub Secret WINDOWS_PFX_BASE64: $base64File"
    Write-Host "`nTo trust this certificate on your local Windows PC (removes 'Unknown Publisher'):" -ForegroundColor Yellow
    Write-Host "  Import-Certificate -FilePath `"$CerPath`" -CertStoreLocation Cert:\CurrentUser\Root"
    Write-Host "  Import-Certificate -FilePath `"$CerPath`" -CertStoreLocation Cert:\CurrentUser\TrustedPublisher"
    exit 0
}

if (-not $FilePath) {
    Write-Error "Please specify -FilePath <path-to-exe> to sign, or -GenerateCert to create a certificate."
}

if (-not (Test-Path $FilePath)) {
    Write-Error "Target executable not found: $FilePath"
}

if (-not (Test-Path $PfxPath)) {
    Write-Error "PFX certificate not found: $PfxPath"
}

# Locate signtool.exe from Windows SDK
$signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $signtool) {
    $sdkPaths = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending
    if ($sdkPaths) {
        $signtool = $sdkPaths[0].FullName
    }
}

if (-not $signtool) {
    Write-Error "signtool.exe not found. Install Windows 10/11 SDK or run inside GitHub Actions windows-latest."
}

Write-Host "Signing $FilePath with $signtool..." -ForegroundColor Cyan
& $signtool sign /f $PfxPath /p $Password /fd SHA256 /tr "http://timestamp.digicert.com" /td SHA256 $FilePath
if ($LASTEXITCODE -ne 0) {
    Write-Error "signtool failed with exit code $LASTEXITCODE"
}
Write-Host "✔ Successfully signed $FilePath" -ForegroundColor Green
