$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root ".local-logs"
$ServerOut = Join-Path $LogDir "server.out.log"
$ServerErr = Join-Path $LogDir "server.err.log"
$EditorOut = Join-Path $LogDir "editor.out.log"
$EditorErr = Join-Path $LogDir "editor.err.log"

$BackendProcess = $null
$FrontendProcess = $null

function Write-Step {
    param([string] $Message)
    Write-Host "  $Message"
}

function Resolve-RequiredCommand {
    param(
        [string[]] $Names,
        [string] $ErrorMessage
    )

    foreach ($Name in $Names) {
        $Command = Get-Command $Name -ErrorAction SilentlyContinue
        if ($Command) {
            if ($Command.Source) {
                return $Command.Source
            }
            return $Command.Path
        }
    }

    throw $ErrorMessage
}

function Stop-ProcessTree {
    param([int] $TargetProcessId)

    if ($TargetProcessId -le 0) {
        return
    }

    & taskkill.exe /PID $TargetProcessId /T /F > $null 2>&1
}

function Stop-PortListener {
    param([int] $Port)

    try {
        $Listeners = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        $ProcessIds = $Listeners | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($ProcessId in $ProcessIds) {
            if ($ProcessId -and $ProcessId -ne $PID) {
                Stop-ProcessTree -TargetProcessId $ProcessId
            }
        }
    } catch {
        # Port cleanup is best-effort; the server will report a clear error if the port is still busy.
    }
}

function Start-HiddenProcess {
    param(
        [string] $FilePath,
        [string[]] $Arguments,
        [string] $WorkingDirectory,
        [string] $OutLog,
        [string] $ErrLog
    )

    Remove-Item -LiteralPath $OutLog, $ErrLog -Force -ErrorAction SilentlyContinue

    Start-Process `
        -FilePath $FilePath `
        -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog `
        -PassThru
}

function Assert-ProcessRunning {
    param(
        [System.Diagnostics.Process] $Process,
        [string] $Name,
        [string] $ErrorLog
    )

    $Process.Refresh()
    if (-not $Process.HasExited) {
        return
    }

    Write-Host ""
    Write-Host "  ERROR: $Name stopped during startup."
    if (Test-Path -LiteralPath $ErrorLog) {
        Write-Host ""
        Write-Host "  Last log lines:"
        Get-Content -LiteralPath $ErrorLog -Tail 30 | ForEach-Object { Write-Host "  $_" }
    }
    throw "$Name failed to start."
}

function Open-Browser {
    Start-Process "http://localhost:3000"
}

function Stop-Services {
    if ($script:FrontendProcess -and -not $script:FrontendProcess.HasExited) {
        Stop-ProcessTree -TargetProcessId $script:FrontendProcess.Id
    }
    if ($script:BackendProcess -and -not $script:BackendProcess.HasExited) {
        Stop-ProcessTree -TargetProcessId $script:BackendProcess.Id
    }
}

try {
    $Banner = Join-Path $Root "banner.ps1"
    if (Test-Path -LiteralPath $Banner) {
        & $Banner
    } else {
        Write-Host ""
        Write-Host "  BLACKNODE"
        Write-Host ""
    }

    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

    $Python = Resolve-RequiredCommand -Names @("python", "py") -ErrorMessage "Python 3.11+ is required."
    $Npm = Resolve-RequiredCommand -Names @("npm.cmd", "npm") -ErrorMessage "npm is required. Install Node.js 20.19+ or 22.12+."

    Write-Step "Checking Python dependencies..."
    & $Python -m pip install -r (Join-Path $Root "editor-server\requirements.txt") -q --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        throw "Python dependency install failed."
    }

    & $Python -c "import importlib.metadata; importlib.metadata.version('blacknode')" > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Step "Installing blacknode package for the CLI..."
        & $Python -m pip install -e $Root -q --disable-pip-version-check
        if ($LASTEXITCODE -ne 0) {
            throw "Blacknode package install failed."
        }
    }

    $NodeModules = Join-Path $Root "editor\node_modules"
    if (-not (Test-Path -LiteralPath $NodeModules)) {
        Write-Step "Installing frontend dependencies (first run, this can take a minute)..."
        Push-Location (Join-Path $Root "editor")
        try {
            & $Npm install
            if ($LASTEXITCODE -ne 0) {
                throw "Frontend dependency install failed."
            }
        } finally {
            Pop-Location
        }
    }

    Write-Step "Done."
    Write-Host ""

    Stop-PortListener -Port 7777

    Write-Step "[1/2] Starting Python server  (http://127.0.0.1:7777)"
    $script:BackendProcess = Start-HiddenProcess `
        -FilePath $Python `
        -Arguments @("server.py") `
        -WorkingDirectory (Join-Path $Root "editor-server") `
        -OutLog $ServerOut `
        -ErrLog $ServerErr

    Start-Sleep -Seconds 3
    Assert-ProcessRunning -Process $script:BackendProcess -Name "Python server" -ErrorLog $ServerErr

    Write-Step "[2/2] Starting visual editor  (http://localhost:3000)"
    $script:FrontendProcess = Start-HiddenProcess `
        -FilePath $Npm `
        -Arguments @("run", "dev", "--", "--strictPort") `
        -WorkingDirectory (Join-Path $Root "editor") `
        -OutLog $EditorOut `
        -ErrLog $EditorErr

    Start-Sleep -Seconds 5
    Assert-ProcessRunning -Process $script:FrontendProcess -Name "Visual editor" -ErrorLog $EditorErr

    Write-Host ""
    Write-Step "Opening browser..."
    Open-Browser
    Write-Host ""
    Write-Step "Logs: .local-logs\server.out.log and .local-logs\editor.out.log"
    Write-Host ""

    while ($true) {
        Assert-ProcessRunning -Process $script:BackendProcess -Name "Python server" -ErrorLog $ServerErr
        Assert-ProcessRunning -Process $script:FrontendProcess -Name "Visual editor" -ErrorLog $EditorErr
        Start-Sleep -Seconds 1
    }
} finally {
    Stop-Services
}
