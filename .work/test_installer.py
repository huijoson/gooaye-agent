import os
import stat
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install-skill.sh"


def run_installer(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    """Helper to run the installer script with consistent environment and options."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [str(INSTALL_SCRIPT)] + args,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=full_env,
    )


def test_installer_is_executable():
    assert INSTALL_SCRIPT.exists()
    st = os.stat(INSTALL_SCRIPT)
    assert bool(st.st_mode & stat.S_IXUSR), "Installer script must be user-executable"


def test_installer_help():
    result = run_installer(["--help"])
    assert result.returncode == 0
    assert "使用方式:" in result.stdout
    assert "--global" in result.stdout
    assert "--target" in result.stdout
    assert "--copy" in result.stdout


def test_installer_target_symlink():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = Path(tmpdir) / "my-target-project"
        target_dir.mkdir()

        result = run_installer(["--target", str(target_dir)])
        assert result.returncode == 0
        assert "已建立符號連結" in result.stdout

        skill_link = target_dir / ".agents" / "skills" / "gooaye"
        assert skill_link.is_symlink()
        assert (skill_link / "SKILL.md").exists()

        # Test idempotency (re-running safely updates)
        result2 = run_installer(["--target", str(target_dir)])
        assert result2.returncode == 0
        assert skill_link.is_symlink()
        assert (skill_link / "SKILL.md").exists()


def test_installer_target_copy():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = Path(tmpdir) / "my-copy-project"
        target_dir.mkdir()

        result = run_installer(["--target", str(target_dir), "--copy"])
        assert result.returncode == 0
        assert "已複製 Gooaye 技能" in result.stdout

        skill_dir = target_dir / ".agents" / "skills" / "gooaye"
        assert skill_dir.is_dir()
        assert not skill_dir.is_symlink()
        assert (skill_dir / "SKILL.md").is_file()


def test_installer_global_mock_home():
    with tempfile.TemporaryDirectory() as mock_home:
        # Create mock antigravity-cli directory in mock HOME
        (Path(mock_home) / ".gemini" / "antigravity-cli").mkdir(parents=True)

        result = run_installer(["--global"], env={"HOME": mock_home})
        assert result.returncode == 0
        assert "全域安裝 (Global)" in result.stdout

        # Verify ~/.gemini/config/skills/gooaye
        gemini_skill = Path(mock_home) / ".gemini" / "config" / "skills" / "gooaye"
        assert gemini_skill.is_symlink()
        assert (gemini_skill / "SKILL.md").exists()

        # Verify ~/.gemini/antigravity-cli/skills/gooaye
        agy_skill = Path(mock_home) / ".gemini" / "antigravity-cli" / "skills" / "gooaye"
        assert agy_skill.is_symlink()
        assert (agy_skill / "SKILL.md").exists()

        # Test idempotency with copy mode
        result_copy = run_installer(["--global", "--copy"], env={"HOME": mock_home})
        assert result_copy.returncode == 0
        assert not gemini_skill.is_symlink()
        assert gemini_skill.is_dir()
        assert (gemini_skill / "SKILL.md").is_file()


def test_installer_invalid_argument():
    result = run_installer(["--unknown-flag"])
    assert result.returncode != 0
    assert "未知參數" in result.stdout or "未知參數" in result.stderr
