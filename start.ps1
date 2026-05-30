$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root ".local-logs"
$ServerOut = Join-Path $LogDir "server.out.log"
$ServerErr = Join-Path $LogDir "server.err.log"
$EditorOut = Join-Path $LogDir "editor.out.log"
$EditorErr = Join-Path $LogDir "editor.err.log"

$BackendProcess = $null
$FrontendProcess = $null
$BackendPort = 7777
$FrontendPort = 3000
$EditorUrl = "http://localhost:$FrontendPort"
$EditorProbeUrls = @("http://127.0.0.1:$FrontendPort", "http://localhost:$FrontendPort")

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
        $Listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
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

function Get-PortProcessIds {
    param([int] $Port)

    try {
        @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)
    } catch {
        @()
    }
}

function Test-PortInUse {
    param([int] $Port)

    return @(Get-PortProcessIds -Port $Port).Count -gt 0
}

function Test-BlacknodeEditorReady {
    foreach ($Url in $EditorProbeUrls) {
        try {
            $Response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($Response.StatusCode -ge 200 -and $Response.Content -match "<title>Blacknode</title>") {
                return $true
            }
        } catch {
            # Try the next loopback spelling before deciding the editor is not ours.
        }
    }

    return $false
}

function Test-BlacknodeEditorProcessOnPort {
    param([int] $Port)

    $EditorDir = (Join-Path $Root "editor").Replace("\", "/").ToLowerInvariant()
    foreach ($ProcessId in @(Get-PortProcessIds -Port $Port)) {
        try {
            $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
            $CommandLine = [string] $ProcessInfo.CommandLine
            $Normalized = $CommandLine.Replace("\", "/").ToLowerInvariant()
            if ($Normalized.Contains($EditorDir) -and $Normalized.Contains("vite")) {
                return $true
            }
        } catch {
            # If process inspection fails, keep the conservative port-busy behavior.
        }
    }

    return $false
}

function Wait-BlacknodeEditorReady {
    param([int] $TimeoutSeconds = 5)

    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $Deadline) {
        if (Test-BlacknodeEditorReady) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }

    return $false
}

function Wait-PortFree {
    param(
        [int] $Port,
        [int] $TimeoutSeconds = 5
    )

    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $Deadline) {
        if (-not (Test-PortInUse -Port $Port)) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }

    return -not (Test-PortInUse -Port $Port)
}

function Write-PortBusyError {
    param([int] $Port)

    Write-Host ""
    Write-Host "  ERROR: Port $Port is already in use by another app."
    $ProcessIds = Get-PortProcessIds -Port $Port
    if (@($ProcessIds).Count -gt 0) {
        Write-Host ""
        Write-Host "  Listening process id(s): $(@($ProcessIds) -join ', ')"
    }
    Write-Host "  Close that app or free port $Port, then run start.bat again."
}

function Test-FrontendDependencies {
    Push-Location (Join-Path $Root "editor")
    try {
        & node -e "import('vite').then(() => {}).catch(() => process.exit(1))" > $null 2>&1
        return $LASTEXITCODE -eq 0
    } finally {
        Pop-Location
    }
}

function Install-FrontendDependencies {
    param([string] $Message)

    Write-Step $Message
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
    if ($env:BLACKNODE_NO_BROWSER -eq "1") {
        Write-Step "Browser launch skipped (BLACKNODE_NO_BROWSER=1)."
        return
    }

    Write-Step "Opening browser..."
    Start-Process $EditorUrl
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

    # Optional: install CuPy for the GPU/CUDA nodes when an NVIDIA GPU is present.
    # Non-fatal: a failure here never blocks the editor.
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        & $Python -c "import cupy" > $null 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Step "NVIDIA GPU detected - installing CuPy for CUDA nodes (one-time, large download)..."
            & $Python -m pip install cupy-cuda12x -q --disable-pip-version-check
            if ($LASTEXITCODE -ne 0) {
                Write-Host "  CuPy install failed; GPU/CUDA nodes stay unavailable but the editor will run." -ForegroundColor Yellow
            }
        }
    }

    $NodeModules = Join-Path $Root "editor\node_modules"
    if (-not (Test-Path -LiteralPath $NodeModules)) {
        Install-FrontendDependencies -Message "Installing frontend dependencies (first run, this can take a minute)..."
    } elseif (-not (Test-FrontendDependencies)) {
        Install-FrontendDependencies -Message "Repairing frontend dependencies for this OS..."
    }

    Write-Step "Done."
    Write-Host ""

    Stop-PortListener -Port $BackendPort

    Write-Step "[1/2] Starting Python server  (http://127.0.0.1:$BackendPort)"
    $script:BackendProcess = Start-HiddenProcess `
        -FilePath $Python `
        -Arguments @("server.py") `
        -WorkingDirectory (Join-Path $Root "editor-server") `
        -OutLog $ServerOut `
        -ErrLog $ServerErr

    Start-Sleep -Seconds 3
    Assert-ProcessRunning -Process $script:BackendProcess -Name "Python server" -ErrorLog $ServerErr

    if (Test-PortInUse -Port $FrontendPort) {
        $ExistingBlacknodeEditor = (Wait-BlacknodeEditorReady) -or (Test-BlacknodeEditorProcessOnPort -Port $FrontendPort)
        if (-not $ExistingBlacknodeEditor) {
            Write-PortBusyError -Port $FrontendPort
            throw "Visual editor port is busy."
        }

        Write-Step "Stopping existing visual editor on port $FrontendPort..."
        Stop-PortListener -Port $FrontendPort
        if (-not (Wait-PortFree -Port $FrontendPort)) {
            Write-PortBusyError -Port $FrontendPort
            throw "Visual editor port is busy."
        }
    }

    Write-Step "[2/2] Starting visual editor  ($EditorUrl)"
    $script:FrontendProcess = Start-HiddenProcess `
        -FilePath $Npm `
        -Arguments @("run", "dev", "--", "--strictPort") `
        -WorkingDirectory (Join-Path $Root "editor") `
        -OutLog $EditorOut `
        -ErrLog $EditorErr

    Start-Sleep -Seconds 5
    Assert-ProcessRunning -Process $script:FrontendProcess -Name "Visual editor" -ErrorLog $EditorErr

    Open-Browser
    Write-Host ""
    Write-Step "Logs: .local-logs\server.out.log and .local-logs\editor.out.log"
    Write-Step "Press Ctrl+C to stop."
    Write-Host ""

    while ($true) {
        Assert-ProcessRunning -Process $script:BackendProcess -Name "Python server" -ErrorLog $ServerErr
        Assert-ProcessRunning -Process $script:FrontendProcess -Name "Visual editor" -ErrorLog $EditorErr
        Start-Sleep -Seconds 1
    }
} finally {
    Stop-Services
}
