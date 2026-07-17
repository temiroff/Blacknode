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
