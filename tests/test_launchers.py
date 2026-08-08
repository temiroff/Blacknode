import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_launchers_create_isolated_environment_and_support_bootstrap_only():
    powershell = (ROOT / "start.ps1").read_text(encoding="utf-8")
    shell = (ROOT / "start.sh").read_text(encoding="utf-8")

    assert 'Join-Path $Root ".venv"' in powershell
    assert " -m venv " in powershell
    assert "BLACKNODE_BOOTSTRAP_ONLY" in powershell
    assert "Test-PythonModule -Python $Python -Name \"blacknode\"" in powershell
    assert 'VENV_DIR="${BLACKNODE_VENV:-$ROOT_DIR/.venv}"' in shell
    assert "BLACKNODE_BOOTSTRAP_ONLY" in shell
    assert "import blacknode, importlib.metadata" in shell


def test_core_launchers_do_not_install_optional_cuda_dependencies():
    powershell = (ROOT / "start.ps1").read_text(encoding="utf-8")
    shell = (ROOT / "start.sh").read_text(encoding="utf-8")

    assert "pip install cupy" not in powershell.lower()
    assert "pip_install cupy" not in shell.lower()


def test_launchers_default_to_the_public_cloud_url_and_allow_overrides():
    powershell = (ROOT / "start.ps1").read_text(encoding="utf-8")
    shell = (ROOT / "start.sh").read_text(encoding="utf-8")

    cloud_url = "https://cloud.blacknoderobotics.com"
    assert f'$DefaultCloudUrl = "{cloud_url}"' in powershell
    assert '[string]::IsNullOrWhiteSpace($env:BLACKNODE_CLOUD_URL)' in powershell
    assert '$env:BLACKNODE_CLOUD_URL = $DefaultCloudUrl' in powershell
    assert f'export BLACKNODE_CLOUD_URL="${{BLACKNODE_CLOUD_URL:-{cloud_url}}}"' in shell


def test_launchers_stream_extension_dependency_setup_output():
    powershell = (ROOT / "start.ps1").read_text(encoding="utf-8")
    shell = (ROOT / "start.sh").read_text(encoding="utf-8")

    assert "& $Python @SetupArguments" in powershell
    assert "Dependency download and installation output will appear below." in powershell
    assert 'output="$(PYTHONPATH="$ROOT_DIR/python" "$PYTHON_BIN" -m blacknode.cli packages setup --missing' not in shell
    assert 'PYTHONPATH="$ROOT_DIR/python" "$PYTHON_BIN" -m blacknode.cli packages setup --missing' in shell


def test_windows_launcher_waits_for_backend_port_cleanup_before_starting():
    powershell = (ROOT / "start.ps1").read_text(encoding="utf-8")

    stop = "Stop-PortListener -Port $BackendPort"
    wait = "Wait-PortFree -Port $BackendPort"
    start = 'Write-Step "[1/2] Starting Python server'

    assert stop in powershell
    assert wait in powershell
    assert powershell.index(stop) < powershell.index(wait) < powershell.index(start)
    assert 'throw "Python server port is busy."' in powershell


def test_windows_launcher_reuses_healthy_services_and_hands_off_cleanly():
    powershell = (ROOT / "start.ps1").read_text(encoding="utf-8")

    reuse = 'Write-Step "Blacknode is already running. Reusing the active services."'
    ownership = "Set-LauncherOwnership"
    stop = "Stop-PortListener -Port $BackendPort"

    assert "Test-BlacknodeBackendReady" in powershell
    assert "Test-BlacknodeEditorReady" in powershell
    assert "BLACKNODE_FORCE_RESTART" in powershell
    assert reuse in powershell
    assert powershell.index(reuse) < powershell.index(ownership, powershell.index(reuse))
    assert powershell.index(ownership, powershell.index(reuse)) < powershell.index(stop)
    assert "Test-LauncherReplaced" in powershell
    assert 'Write-Step "Blacknode was restarted by another launcher."' in powershell


def test_windows_launcher_adopts_a_healthy_replacement_service():
    powershell = (ROOT / "start.ps1").read_text(encoding="utf-8")

    assert "if (& $ReadyProbe)" in powershell
    assert "$ReplacementIds = @(Get-PortProcessIds -Port $Port)" in powershell
    assert '$script:BackendProcess = $Replacement' in powershell
    assert '$script:FrontendProcess = $Replacement' in powershell
    assert 'Write-Step "$Name restarted; launcher adopted process $($Replacement.Id)."' in powershell
    assert '-Service "backend"' in powershell
    assert '-ReadyProbe { Test-BlacknodeBackendReady }' in powershell
    assert '-Service "frontend"' in powershell
    assert '-ReadyProbe { Test-BlacknodeEditorReady }' in powershell


def test_windows_starter_always_restarts_running_services():
    batch = (ROOT / "start.bat").read_text(encoding="utf-8")

    force_restart = 'set "BLACKNODE_FORCE_RESTART=1"'
    launch = 'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"'

    assert force_restart in batch
    assert batch.index(force_restart) < batch.index(launch)


def test_windows_markdown_launch_commands_are_powershell_explicit():
    markdown_files = [ROOT / "README.md", *ROOT.joinpath("docs").rglob("*.md")]
    markdown_files.extend([
        ROOT / "skills" / "blacknode-workflow" / "SKILL.md",
        ROOT / ".agents" / "skills" / "blacknode-workflow" / "SKILL.md",
    ])

    ambiguous = []
    for path in markdown_files:
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?<!\.\\)start\.bat", text):
            ambiguous.append(str(path.relative_to(ROOT)))

    assert ambiguous == []
