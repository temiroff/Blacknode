$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Write-ComposeHint {
    param(
        [string] $Title,
        [string[]] $Details = @(),
        [string[]] $Fixes = @()
    )

    Write-Host ""
    Write-Host "ERROR: $Title"
    foreach ($Detail in $Details) {
        if ($Detail) {
            Write-Host "  $Detail"
        }
    }

    if ($Fixes.Count -gt 0) {
        Write-Host ""
        Write-Host "Fix:"
        foreach ($Fix in $Fixes) {
            Write-Host "  - $Fix"
        }
    }

    Write-Host ""
}

function Invoke-Captured {
    param([string[]] $Command)

    $PreviousErrorActionPreference = $ErrorActionPreference
    $Output = @()
    $ExitCode = 1
    try {
        $ErrorActionPreference = "Continue"
        $Arguments = if ($Command.Count -gt 1) { @($Command[1..($Command.Count - 1)]) } else { @() }
        $Output = & $Command[0] @Arguments 2>&1
        $ExitCode = $LASTEXITCODE
    } catch {
        $Output += $_.Exception.Message
        if ($LASTEXITCODE) {
            $ExitCode = $LASTEXITCODE
        }
    } finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }

    return @{
        ExitCode = $ExitCode
        Output = @($Output | ForEach-Object { $_.ToString() })
    }
}

$Docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $Docker) {
    Write-ComposeHint `
        -Title "Docker CLI was not found." `
        -Fixes @(
            "Install Docker Desktop for Windows.",
            "Reopen this terminal after installation so docker.exe is on PATH."
        )
    exit 1
}

$DockerExe = if ($Docker.Source) { $Docker.Source } else { $Docker.Path }

$ComposeVersion = Invoke-Captured @($DockerExe, "compose", "version")
if ($ComposeVersion.ExitCode -ne 0) {
    Write-ComposeHint `
        -Title "Docker Compose v2 is not available." `
        -Details $ComposeVersion.Output `
        -Fixes @(
            "Update Docker Desktop.",
            "Confirm 'docker compose version' works before starting Blacknode."
        )
    exit $ComposeVersion.ExitCode
}

$DockerInfo = Invoke-Captured @($DockerExe, "info", "--format", "{{.ServerVersion}}")
if ($DockerInfo.ExitCode -ne 0) {
    $OutputText = ($DockerInfo.Output -join "`n")
    $PipeMissing = $OutputText -match "dockerDesktopLinuxEngine|//\./pipe|open //|The system cannot find the file specified"
    $Details = @("Docker CLI is installed, but the Docker engine is not reachable.")
    $DockerMessage = @($DockerInfo.Output | Where-Object { $_.Trim() } | Select-Object -First 1)
    if ($DockerMessage.Count -gt 0) {
        $Details += "Docker said: $($DockerMessage[0])"
    }

    $Fixes = if ($PipeMissing) {
        @(
            "Start Docker Desktop and wait until it says Docker Desktop is running.",
            "Make sure Docker Desktop is using Linux containers.",
            "If Docker Desktop is stuck, run 'wsl --shutdown', reopen Docker Desktop, then retry '.\docker-up.ps1'."
        )
    } else {
        @(
            "Start Docker Desktop or your Docker engine.",
            "Confirm 'docker info' works before starting Blacknode.",
            "If you use a remote Docker context, switch to a reachable context with 'docker context use <name>'."
        )
    }

    Write-ComposeHint `
        -Title "Docker engine is not running or not reachable." `
        -Details $Details `
        -Fixes $Fixes
    exit $DockerInfo.ExitCode
}

Push-Location $Root
try {
    & $DockerExe compose up --build @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
