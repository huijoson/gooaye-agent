import os
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install-skill.sh"


def test_installer_help():
    result = subprocess.run(
        [str(INSTALL_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0
    assert "使用方式:" in result.stdout
    assert "--global" in result.stdout
    assert "--target" in result.stdout
    assert "--copy" in result.stdout


def test_installer_target_symlink():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = Path(tmpdir) / "my-target-project"
        target_dir.mkdir()

        result = subprocess.run(
            [str(INSTALL_SCRIPT), "--target", str(target_dir)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        assert "已建立符號連結" in result.stdout

        skill_link = target_dir / ".agents" / "skills" / "gooaye"
        assert skill_link.is_symlink()
        assert (skill_link / "SKILL.md").exists()

        # Test idempotency (running again safely updates)
        result2 = subprocess.run(
            [str(INSTALL_SCRIPT), "--target", str(target_dir)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result2.returncode == 0
        assert skill_link.is_symlink()
        assert (skill_link / "SKILL.md").exists()


def test_installer_target_copy():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = Path(tmpdir) / "my-copy-project"
        target_dir.mkdir()

        result = subprocess.run(
            [str(INSTALL_SCRIPT), "--target", str(target_dir), "--copy"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        assert "已複製 Gooaye 技能" in result.stdout

        skill_dir = target_dir / ".agents" / "skills" / "gooaye"
        assert skill_dir.is_dir()
        assert not skill_dir.is_symlink()
        assert (skill_dir / "SKILL.md").is_file()


def test_installer_invalid_argument():
    result = subprocess.run(
        [str(INSTALL_SCRIPT), "--unknown-flag"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode != 0
    assert "未知參數" in result.stdout or "未知參數" in result.stderr
