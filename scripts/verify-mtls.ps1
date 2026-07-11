param(
    [string]$CertsDir = "certs",
    [string]$CharonHost = "localhost",
    [int]$CharonPort = 50051,
    [string]$JudyHost = "host.docker.internal",
    [int]$JudyPort = 50052,
    [switch]$SkipHandshake
)

$ErrorActionPreference = "Stop"

function Invoke-External {
    param(
        [string]$Command,
        [string[]]$Arguments,
        [string]$FailureMessage
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

function Test-RequiredFile {
    param([string]$Path)

    if (-not (Test-Path -Path $Path -PathType Leaf)) {
        throw "Missing required file: $Path"
    }
}

if (-not (Get-Command openssl -ErrorAction SilentlyContinue)) {
    throw "OpenSSL is required. Install OpenSSL and ensure 'openssl' is on PATH."
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$certsRoot = Join-Path $repoRoot $CertsDir

$clientsCaCert = Join-Path $certsRoot "ca/clients-ca.crt"
$judyCaCert = Join-Path $certsRoot "ca/judy-ca.crt"
$charonServerCaCert = Join-Path $certsRoot "ca/charon-server-ca.crt"

$charonServerCert = Join-Path $certsRoot "charon/server.crt"
$charonServerKey = Join-Path $certsRoot "charon/server.key"
$charonClientCert = Join-Path $certsRoot "charon/client.crt"
$charonClientKey = Join-Path $certsRoot "charon/client.key"

$judyServerCert = Join-Path $certsRoot "judy/server.crt"
$clientsCallerCert = Join-Path $certsRoot "clients/caller.crt"
$clientsCallerKey = Join-Path $certsRoot "clients/caller.key"

$requiredFiles = @(
    $clientsCaCert,
    $judyCaCert,
    $charonServerCaCert,
    $charonServerCert,
    $charonServerKey,
    $charonClientCert,
    $charonClientKey,
    $judyServerCert,
    $clientsCallerCert,
    $clientsCallerKey
)

foreach ($path in $requiredFiles) {
    Test-RequiredFile -Path $path
}

Write-Host "[1/4] Verifying certificate trust chains..."
Invoke-External -Command "openssl" -Arguments @("verify", "-CAfile", $charonServerCaCert, $charonServerCert) -FailureMessage "Charon server cert failed CA validation"
Invoke-External -Command "openssl" -Arguments @("verify", "-CAfile", $judyCaCert, $judyServerCert) -FailureMessage "Judy server cert failed CA validation"
Invoke-External -Command "openssl" -Arguments @("verify", "-CAfile", $judyCaCert, $charonClientCert) -FailureMessage "Charon client cert failed Judy CA validation"
Invoke-External -Command "openssl" -Arguments @("verify", "-CAfile", $clientsCaCert, $clientsCallerCert) -FailureMessage "Caller client cert failed Clients CA validation"

if ($SkipHandshake) {
    Write-Host "[2/4] Handshake checks skipped (--SkipHandshake)."
    Write-Host "mTLS certificate integrity checks passed."
    exit 0
}

Write-Host "[2/4] Checking Charon inbound mTLS handshake..."
Invoke-External -Command "openssl" -Arguments @(
    "s_client",
    "-connect", "$CharonHost`:$CharonPort",
    "-CAfile", $charonServerCaCert,
    "-cert", $clientsCallerCert,
    "-key", $clientsCallerKey,
    "-verify_return_error",
    "-brief"
) -FailureMessage "Failed mTLS handshake to Charon at $CharonHost:$CharonPort"

Write-Host "[3/4] Checking Judy outbound mTLS handshake path from Charon identity..."
Invoke-External -Command "openssl" -Arguments @(
    "s_client",
    "-connect", "$JudyHost`:$JudyPort",
    "-CAfile", $judyCaCert,
    "-cert", $charonClientCert,
    "-key", $charonClientKey,
    "-verify_return_error",
    "-brief"
) -FailureMessage "Failed mTLS handshake to Judy at $JudyHost:$JudyPort"

Write-Host "[4/4] mTLS verification completed successfully."
