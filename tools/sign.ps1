<#
  Підпис EXE самопідписаним сертифікатом ГС «УАІТ» (Authenticode).

  powershell -ExecutionPolicy Bypass -File tools\sign.ps1 [-ExePath dist\SkanerShkola.exe] [-InstallTrust] [-ExportPfx]

  - Створює (або повторно використовує) сертифікат підпису коду "CN=ГС УАІТ" у CurrentUser\My, строк 5 років.
  - Якщо поруч лежить certs\UAIT_CodeSigning.pfx — бере його (однаковий підпис на всіх ПК збірки).
  - Підписує EXE з позначкою часу (якщо є інтернет).
  - -InstallTrust: довіряти сертифікату на цьому ПК (Root + TrustedPublisher) — без «Невідомий видавець».
  - -ExportPfx: зберегти certs\UAIT_CodeSigning.pfx (з закритим ключем) і .cer (для розсилки на інші ПК).

  Увага: самопідписаний сертифікат не прибирає SmartScreen на чужих ПК, доки .cer не імпортовано
  в довірені (вручну або через групову політику домену).
#>
param(
    [string]$ExePath = "dist\SkanerShkola.exe",
    [string]$PfxPassword = "uait-skaner",
    [switch]$InstallTrust,
    [switch]$ExportPfx
)
$ErrorActionPreference = "Stop"
$Subject = "CN=ГС УАІТ, O=ГС УАІТ, C=UA"
$Root = Split-Path $PSScriptRoot -Parent
$CertDir = Join-Path $Root "certs"
$PfxFile = Join-Path $CertDir "UAIT_CodeSigning.pfx"
$CerFile = Join-Path $CertDir "UAIT_CodeSigning.cer"
if (-not [IO.Path]::IsPathRooted($ExePath)) { $ExePath = Join-Path $Root $ExePath }
if (-not (Test-Path $ExePath)) { Write-Error "Не знайдено $ExePath. Спершу build.bat."; exit 1 }

$sec = ConvertTo-SecureString $PfxPassword -AsPlainText -Force
$cert = $null
if (Test-Path $PfxFile) {
    $cert = Import-PfxCertificate -FilePath $PfxFile -CertStoreLocation Cert:\CurrentUser\My -Password $sec -Exportable
    Write-Host "[1/3] Сертифікат з $PfxFile" -ForegroundColor Cyan
} else {
    $cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Subject -eq $Subject -and $_.NotAfter -gt (Get-Date) } |
        Sort-Object NotAfter -Descending | Select-Object -First 1
    if (-not $cert) {
        $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $Subject `
            -FriendlyName "ГС УАІТ — підпис коду" -CertStoreLocation Cert:\CurrentUser\My `
            -KeyAlgorithm RSA -KeyLength 3072 -HashAlgorithm SHA256 `
            -KeyExportPolicy Exportable -NotAfter (Get-Date).AddYears(5)
        Write-Host "[1/3] Створено сертифікат $($cert.Thumbprint)" -ForegroundColor Green
    } else {
        Write-Host "[1/3] Наявний сертифікат $($cert.Thumbprint) (до $($cert.NotAfter))" -ForegroundColor Cyan
    }
}

if ($InstallTrust) {
    foreach ($storeName in "Root", "TrustedPublisher") {
        $st = New-Object System.Security.Cryptography.X509Certificates.X509Store($storeName, "CurrentUser")
        $st.Open("ReadWrite"); $st.Add($cert); $st.Close()
    }
    Write-Host "      Сертифікат довірений на цьому ПК" -ForegroundColor Green
}

Write-Host "[2/3] Підписую $ExePath" -ForegroundColor Cyan
$res = $null
foreach ($tsa in "http://timestamp.digicert.com", "http://timestamp.sectigo.com") {
    try { $res = Set-AuthenticodeSignature -FilePath $ExePath -Certificate $cert -HashAlgorithm SHA256 -TimestampServer $tsa; break } catch { }
}
if (-not $res) {
    Write-Host "      Сервер часу недоступний — підпис без позначки часу" -ForegroundColor Yellow
    $res = Set-AuthenticodeSignature -FilePath $ExePath -Certificate $cert -HashAlgorithm SHA256
}
Write-Host "      Статус: $($res.Status) $($res.StatusMessage)"

if ($ExportPfx) {
    New-Item -ItemType Directory -Force $CertDir | Out-Null
    Export-PfxCertificate -Cert $cert -FilePath $PfxFile -Password $sec | Out-Null
    Export-Certificate -Cert $cert -FilePath $CerFile | Out-Null
    Write-Host "[3/3] Збережено $PfxFile і $CerFile (pfx — тримати в секреті, у git не додається)" -ForegroundColor Green
} else {
    Write-Host "[3/3] Експорт пропущено (-ExportPfx, щоб зберегти)" -ForegroundColor DarkGray
}
if ($res.Status -eq "HashMismatch" -or $res.Status -eq "NotSigned") { exit 2 }
