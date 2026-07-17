$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root ".local-logs"
$ServerOut = Join-Path $LogDir "server.out.log"
$ServerErr = Join-Path $LogDir "server.err.log"
$EditorOut = Join-Path $LogDir "editor.out.log"
$EditorErr = Join-Path $LogDir "editor.err.log"
$VenvDir = if ($env:BLACKNODE_VENV) { $env:BLACKNODE_VENV } else { Join-Path $Root ".venv" }

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

function Assert-PythonVersion {
    param([string] $Python)

    if (-not (Invoke-NativeProbe -Command $Python -Arguments @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"))) {
        $Version = & $Python --version 2>&1
        throw "Python 3.11+ is required. Found: $Version"
    }
}

function Resolve-ProjectPython {
    $SystemPython = Resolve-RequiredCommand -Names @("python", "py") -ErrorMessage "Python 3.11+ is required."
    Assert-PythonVersion -Python $SystemPython

    $VenvPython = Join-Path $VenvDir "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Write-Step "Creating Python virtual environment (.venv)..."
        & $SystemPython -m venv $VenvDir
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VenvPython)) {
            throw "Could not create the Python virtual environment at $VenvDir."
        }
    }

    Assert-PythonVersion -Python $VenvPython
    return $VenvPython
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
    Write-Host "  Close that app or free port $Port, then run .\start.bat again."
}

function Invoke-NativeProbe {
    param(
        [string] $Command,
        [string[]] $Arguments
    )

    $PreviousErrorActionPreference = $ErrorActionPreference
    $HadNativePreference = Test-Path Variable:PSNativeCommandUseErrorActionPreference
    if ($HadNativePreference) {
        $PreviousNativePreference = $PSNativeCommandUseErrorActionPreference
    }

    try {
        $ErrorActionPreference = "Continue"
        if ($HadNativePreference) {
            $PSNativeCommandUseErrorActionPreference = $false
        }
        & $Command @Arguments > $null 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        if ($HadNativePreference) {
            $PSNativeCommandUseErrorActionPreference = $PreviousNativePreference
        }
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
}

function Test-PythonDistribution {
    param(
        [string] $Python,
        [string] $Name
    )

    $Probe = "import importlib.metadata as metadata, sys; name = sys.argv[1].lower(); sys.exit(0 if any((dist.metadata.get('Name') or '').lower() == name for dist in metadata.distributions()) else 1)"
    return Invoke-NativeProbe -Command $Python -Arguments @("-c", $Probe, $Name)
}

function Test-PythonModule {
    param(
        [string] $Python,
        [string] $Name
    )

    $Probe = "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)"
    return Invoke-NativeProbe -Command $Python -Arguments @("-c", $Probe, $Name)
}

function Test-FrontendDependencies {
    Push-Location (Join-Path $Root "editor")
    try {
        return Invoke-NativeProbe -Command "node" -Arguments @("-e", "import('vite').then(() => {}).catch(() => process.exit(1))")
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

function Invoke-PythonCapture {
    param([string[]] $Arguments)

    # Windows PowerShell wraps native stderr as NativeCommandError records.
    # Package managers legitimately use stderr for warnings, so capture with a
    # non-terminating preference and decide success from the process exit code.
    $PreviousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $CapturedOutput = @(& $Python @Arguments 2>&1)
        $CapturedExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
    return [PSCustomObject]@{
        Output = $CapturedOutput
        ExitCode = $CapturedExitCode
    }
}

function Invoke-PackageHealthCheck {
    if ($env:BLACKNODE_SKIP_PACKAGE_CHECK -eq "1") {
        Write-Step "Package health check skipped (BLACKNODE_SKIP_PACKAGE_CHECK=1)."
        return
    }

    $PreviousPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = Join-Path $Root "python"
    try {
        if ($env:BLACKNODE_PACKAGE_AUTO_UPDATE -ne "0") {
            Write-Step "Updating extension packages (safe fast-forward only)..."
            $Result = Invoke-PythonCapture -Arguments @("-m", "blacknode.cli", "packages", "update", "--all")
            $Output = $Result.Output
            $ExitCode = $Result.ExitCode
            if ($Output) { $Output | ForEach-Object { Write-Host "    $_" } }
            if ($ExitCode -ne 0) {
                Write-Host "  Warning: package update failed." -ForegroundColor Yellow
            }
        }

        if ($env:BLACKNODE_PACKAGE_AUTO_SETUP -ne "0") {
            Write-Step "Installing missing extension package dependencies..."
            $SetupResult = Invoke-PythonCapture -Arguments @("-m", "blacknode.cli", "packages", "setup", "--missing")
            $SetupOutput = $SetupResult.Output
            $SetupExitCode = $SetupResult.ExitCode
            if ($SetupOutput) { $SetupOutput | ForEach-Object { Write-Host "    $_" } }
            if ($SetupExitCode -ne 0) {
                Write-Host "  Warning: automatic package dependency setup failed; startup will continue." -ForegroundColor Yellow
            }
        }

        Write-Step "Checking package health..."
        $Args = @("-m", "blacknode.cli", "packages", "status")
        if ($env:BLACKNODE_PACKAGE_AUTO_UPDATE -eq "0" -and $env:BLACKNODE_PACKAGE_CHECK_REMOTE -eq "1") {
            $Args += "--fetch"
        }
        $Result = Invoke-PythonCapture -Arguments $Args
        $Output = $Result.Output
        $ExitCode = $Result.ExitCode
        $Text = ($Output -join "`n")
        if ($ExitCode -ne 0) {
            Write-Host "  Warning: package health check failed:" -ForegroundColor Yellow
            if ($Output) { $Output | ForEach-Object { Write-Host "    $_" } }
            return
        }
        if ($Text -match "\[FAILED\]|\[ok, warnings\]|\[ok, nodes missing\]|behind|dirty|ahead|^  ! ") {
            Write-Host "  Package health warnings:" -ForegroundColor Yellow
            if ($Output) { $Output | ForEach-Object { Write-Host "    $_" } }
            if ($env:BLACKNODE_PACKAGE_AUTO_UPDATE -ne "0") {
                Write-Host "  Auto-update skipped dirty, ahead, or blocked packages. Resolve the listed package state, then restart."
            } else {
                Write-Host "  Use: blacknode packages update --all"
            }
        } else {
            Write-Step "Package health OK."
        }
    } finally {
        $env:PYTHONPATH = $PreviousPythonPath
    }
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

    $Python = Resolve-ProjectPython
    $Npm = Resolve-RequiredCommand -Names @("npm.cmd", "npm") -ErrorMessage "npm is required. Install Node.js 20.19+ or 22.12+."

    Write-Step "Checking Python dependencies..."
    & $Python -m pip install -r (Join-Path $Root "editor-server\requirements.txt") -q --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        throw "Python dependency install failed."
    }

    if ((-not (Test-PythonDistribution -Python $Python -Name "blacknode")) -or
        (-not (Test-PythonModule -Python $Python -Name "blacknode"))) {
        Write-Step "Installing blacknode package for the CLI..."
        & $Python -m pip install -e $Root -q --disable-pip-version-check
        if ($LASTEXITCODE -ne 0) {
            throw "Blacknode package install failed."
        }
    }

    Invoke-PackageHealthCheck

    $NodeModules = Join-Path $Root "editor\node_modules"
    if (-not (Test-Path -LiteralPath $NodeModules)) {
        Install-FrontendDependencies -Message "Installing frontend dependencies (first run, this can take a minute)..."
    } elseif (-not (Test-FrontendDependencies)) {
        Install-FrontendDependencies -Message "Repairing frontend dependencies for this OS..."
    }

    Write-Step "Done."
    Write-Host ""

    if ($env:BLACKNODE_BOOTSTRAP_ONLY -eq "1") {
        Write-Step "Bootstrap complete (BLACKNODE_BOOTSTRAP_ONLY=1)."
        return
    }

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
