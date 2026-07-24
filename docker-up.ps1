[CmdletBinding()]
param(
    [switch] $RepairWsl,
    [switch] $CheckOnly,
    [ValidateRange(10, 300)]
    [int] $ReadyTimeoutSeconds = 90,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $ComposeArguments = @()
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$DockerProbeTimeoutMs = 8000
$Mutex = $null
$HasMutex = $false

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
    param(
        [string[]] $Command,
        [int] $TimeoutMs = 10000
    )

    $StartInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $StartInfo.FileName = $Command[0]
    $StartInfo.UseShellExecute = $false
    $StartInfo.CreateNoWindow = $true
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true

    $Arguments = if ($Command.Count -gt 1) {
        @($Command[1..($Command.Count - 1)])
    } else {
        @()
    }
    if ($StartInfo.PSObject.Properties.Name -contains "ArgumentList") {
        foreach ($Argument in $Arguments) {
            $StartInfo.ArgumentList.Add([string] $Argument)
        }
    } else {
        $StartInfo.Arguments = (
            $Arguments | ForEach-Object {
                '"' + ([string] $_).Replace('"', '\"') + '"'
            }
        ) -join " "
    }

    $Process = [System.Diagnostics.Process]::new()
    $Process.StartInfo = $StartInfo
    try {
        if (-not $Process.Start()) {
            throw "Could not start $($Command[0])."
        }
        $OutputTask = $Process.StandardOutput.ReadToEndAsync()
        $ErrorTask = $Process.StandardError.ReadToEndAsync()
        $TimedOut = -not $Process.WaitForExit($TimeoutMs)
        if ($TimedOut) {
            try {
                $Process.Kill($true)
            } catch {
                $Process.Kill()
            }
            $Process.WaitForExit()
        }
        $OutputText = $OutputTask.GetAwaiter().GetResult()
        $ErrorText = $ErrorTask.GetAwaiter().GetResult()
        $Lines = @(
            @($OutputText, $ErrorText) |
                Where-Object { $_ } |
                ForEach-Object { $_ -split "\r?\n" } |
                Where-Object { $_ }
        )
        return @{
            ExitCode = if ($TimedOut) { 124 } else { $Process.ExitCode }
            TimedOut = $TimedOut
            Output = $Lines
        }
    } catch {
        return @{
            ExitCode = 1
            TimedOut = $false
            Output = @($_.Exception.Message)
        }
    } finally {
        $Process.Dispose()
    }
}

function Find-DockerDesktop {
    $Candidates = @()
    if ($env:ProgramFiles) {
        $Candidates += Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    }
    if ($env:LOCALAPPDATA) {
        $Candidates += Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe"
    }
    return $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

function Find-DockerCli {
    $Desktop = Find-DockerDesktop
    if (-not $Desktop) {
        return $null
    }
    $Candidate = Join-Path (Split-Path -Parent $Desktop) "DockerCli.exe"
    if (Test-Path -LiteralPath $Candidate) {
        return $Candidate
    }
    return $null
}

function Get-DockerDesktopProcesses {
    return @(
        Get-Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ProcessName -in @(
                    "Docker Desktop",
                    "com.docker.backend",
                    "com.docker.build",
                    "docker-agent",
                    "docker-sandbox"
                )
            }
    )
}

function Start-DockerDesktop {
    if ((Get-DockerDesktopProcesses).Count -gt 0) {
        return
    }
    $Desktop = Find-DockerDesktop
    if (-not $Desktop) {
        throw "Docker Desktop is installed, but Docker Desktop.exe could not be found."
    }
    Write-Host "Starting Docker Desktop..."
    Start-Process -FilePath $Desktop -WindowStyle Hidden | Out-Null
}

function Get-RunningNonDockerWslDistros {
    $Result = Invoke-Captured @("wsl.exe", "--list", "--running", "--quiet") 5000
    if ($Result.ExitCode -ne 0) {
        return @("unknown")
    }
    return @(
        $Result.Output |
            ForEach-Object {
                ([string] $_).Replace(([char] 0).ToString(), "").Trim()
            } |
            Where-Object { $_ -and $_ -ne "docker-desktop" }
    )
}

function Repair-DockerWslEngine {
    Write-Host "Repairing the stuck Docker Desktop WSL engine..."
    $DockerCli = Find-DockerCli
    if ($DockerCli) {
        $null = Invoke-Captured @($DockerCli, "-Shutdown") 15000
    }

    $Processes = Get-DockerDesktopProcesses
    if ($Processes.Count -gt 0) {
        $Processes | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }

    $Shutdown = Invoke-Captured @("wsl.exe", "--shutdown") 20000
    if ($Shutdown.ExitCode -ne 0) {
        throw "WSL shutdown failed: $($Shutdown.Output -join ' ')"
    }
    Start-DockerDesktop
}

function Get-DockerEngineProbe {
    param([string] $DockerExe)
    return Invoke-Captured @(
        $DockerExe,
        "info",
        "--format",
        "{{.ServerVersion}}"
    ) $DockerProbeTimeoutMs
}

function Wait-DockerEngine {
    param(
        [string] $DockerExe,
        [int] $TimeoutSeconds
    )

    $Deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $LastProbe = $null
    do {
        $LastProbe = Get-DockerEngineProbe $DockerExe
        if ($LastProbe.ExitCode -eq 0) {
            return $LastProbe
        }
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $Deadline)
    return $LastProbe
}

try {
    $Mutex = [System.Threading.Mutex]::new($false, "Local\BlacknodeDockerUp")
    try {
        $HasMutex = $Mutex.WaitOne(0)
    } catch [System.Threading.AbandonedMutexException] {
        $HasMutex = $true
    }
    if (-not $HasMutex) {
        Write-ComposeHint `
            -Title "Another Blacknode Docker launcher is already running." `
            -Fixes @(
                "Use the existing terminal instead of starting Docker twice.",
                "Run '.\docker-down.ps1' from a separate terminal when you want to stop the stack."
            )
        exit 1
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

    $ComposeVersion = Invoke-Captured @($DockerExe, "compose", "version") 10000
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

    $InitialProbe = Get-DockerEngineProbe $DockerExe
    if ($InitialProbe.ExitCode -ne 0) {
        $DesktopProcesses = Get-DockerDesktopProcesses
        $NonDockerDistros = Get-RunningNonDockerWslDistros
        $DesktopStart = $DesktopProcesses |
            Where-Object { $_.StartTime } |
            Sort-Object StartTime |
            Select-Object -First 1
        $DesktopStuck = (
            $DesktopStart -and
            $DesktopStart.StartTime -lt (Get-Date).AddMinutes(-1)
        )
        $SafeAutomaticRepair = $DesktopStuck -and $NonDockerDistros.Count -eq 0

        if ($RepairWsl -or $SafeAutomaticRepair) {
            if ($SafeAutomaticRepair -and -not $RepairWsl) {
                Write-Host "Docker Desktop has been unresponsive for more than one minute."
                Write-Host "No other WSL distribution is running, so Blacknode can safely reset Docker's WSL engine."
            }
            Repair-DockerWslEngine
        } elseif ($DesktopProcesses.Count -eq 0) {
            Start-DockerDesktop
        } elseif ($NonDockerDistros.Count -gt 0) {
            Write-ComposeHint `
                -Title "Docker Desktop is stuck while another WSL distribution is running." `
                -Details @(
                    "Running WSL distributions: $($NonDockerDistros -join ', ')",
                    "Blacknode did not stop them automatically."
                ) `
                -Fixes @(
                    "Save work in those WSL distributions.",
                    "Run '.\docker-up.ps1 -RepairWsl' to reset WSL and restart Docker Desktop."
                )
            exit 1
        }

        Write-Host "Waiting up to $ReadyTimeoutSeconds seconds for the Docker engine..."
        $DockerInfo = Wait-DockerEngine $DockerExe $ReadyTimeoutSeconds
    } else {
        $DockerInfo = $InitialProbe
    }

    if ($DockerInfo.ExitCode -ne 0) {
        $Details = @("Docker Desktop started, but its engine did not become ready.")
        if ($DockerInfo.TimedOut) {
            $Details += "The Docker CLI probe timed out instead of freezing this launcher."
        }
        $DockerMessage = @(
            $DockerInfo.Output |
                Where-Object { $_.Trim() } |
                Select-Object -First 1
        )
        if ($DockerMessage.Count -gt 0) {
            $Details += "Docker said: $($DockerMessage[0])"
        }
        Write-ComposeHint `
            -Title "Docker engine startup timed out." `
            -Details $Details `
            -Fixes @(
                "Run '.\docker-up.ps1 -RepairWsl' after saving work in other WSL distributions.",
                "Open Docker Desktop Troubleshoot if the repair still fails."
            )
        exit 1
    }

    $ServerVersion = @($DockerInfo.Output | Where-Object { $_.Trim() } | Select-Object -First 1)
    $VersionSuffix = if ($ServerVersion.Count -gt 0) {
        " (server $($ServerVersion[0]))"
    } else {
        ""
    }
    Write-Host "Docker engine ready$VersionSuffix."

    if ($CheckOnly) {
        exit 0
    }

    Push-Location $Root
    try {
        & $DockerExe compose up --build --remove-orphans @ComposeArguments
        exit $LASTEXITCODE
    } finally {
        Pop-Location
    }
} finally {
    if ($HasMutex -and $Mutex) {
        try {
            $Mutex.ReleaseMutex()
        } catch {
            # The process is already exiting; there is nothing left to release.
        }
    }
    if ($Mutex) {
        $Mutex.Dispose()
    }
}
