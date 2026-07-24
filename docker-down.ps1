[CmdletBinding()]
param(
    [switch] $Volumes
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$DockerCheck = Join-Path $Root "docker-up.ps1"

& $DockerCheck -CheckOnly -ReadyTimeoutSeconds 30
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$Docker = Get-Command docker -ErrorAction SilentlyContinue

if (-not $Docker) {
    Write-Host "ERROR: Docker CLI was not found."
    exit 1
}

$DockerExe = if ($Docker.Source) { $Docker.Source } else { $Docker.Path }
$ComposeArguments = @("compose", "down", "--remove-orphans")
if ($Volumes) {
    $ComposeArguments += "--volumes"
}

Push-Location $Root
try {
    & $DockerExe @ComposeArguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
