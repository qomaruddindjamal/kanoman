import subprocess
import pytest
from pathlib import Path
from kanoman.config.settings import KanomanConfig
from kanoman.git.controller import GitController
from kanoman.git.models import GitOperationMode


@pytest.fixture
def temp_git_repo(tmp_path: Path):
    """Create a clean local git repository for testing controller isolation."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=str(repo_dir), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@kanoman.local"],
        cwd=str(repo_dir),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/qomaruddindjamal/kanoman.git"],
        cwd=str(repo_dir),
        check=True,
        capture_output=True,
    )
    return repo_dir


def test_git_controller_prohibits_destructive_flags(temp_git_repo: Path):
    ctrl = GitController(
        workspace_root=temp_git_repo,
        allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
    )
    with pytest.raises(ValueError, match="Destructive command 'git reset --hard' is strictly prohibited"):
        ctrl._run_git(["reset", "--hard", "HEAD~1"])

    with pytest.raises(ValueError, match="Prohibited destructive Git flag detected"):
        ctrl._run_git(["push", "--force", "origin", "main"])


def test_git_controller_rejects_unauthorized_remote(temp_git_repo: Path):
    # Controller expects kanoman, but we set different allowed_remote
    ctrl = GitController(
        workspace_root=temp_git_repo,
        allowed_remote="https://github.com/other-org/other-repo.git",
    )
    with pytest.raises(ValueError, match="Remote URL mismatch"):
        ctrl.verify_repository_identity()


def test_git_controller_rejects_unauthorized_root(tmp_path: Path):
    wrong_dir = tmp_path / "not_a_repo"
    wrong_dir.mkdir()
    ctrl = GitController(
        workspace_root=wrong_dir,
        allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
    )
    with pytest.raises(ValueError, match="is not a valid Git repository"):
        ctrl.verify_repository_identity()


def test_git_controller_dry_run_does_not_mutate(temp_git_repo: Path):
    ctrl = GitController(
        workspace_root=temp_git_repo,
        allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
    )
    test_file = temp_git_repo / "hello.txt"
    test_file.write_text("Hello Kanoman", encoding="utf-8")

    plan = ctrl.dry_run(["hello.txt"], "Add hello.txt")
    assert plan.mode == GitOperationMode.DRY_RUN
    assert plan.is_safe is True

    # Verify nothing was committed
    status = ctrl.inspect()
    assert "hello.txt" in status.untracked_files
    assert status.latest_commit_sha is None


def test_git_controller_safe_commit_success(temp_git_repo: Path):
    config = KanomanConfig(git_dry_run=False)
    ctrl = GitController(
        workspace_root=temp_git_repo,
        allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
        config=config,
    )
    test_file = temp_git_repo / "doc.txt"
    test_file.write_text("Safe documentation file.", encoding="utf-8")

    result = ctrl.safe_commit(["doc.txt"], "Add documentation", dry_run=False)
    assert result.success is True
    assert result.commit_sha is not None

    status = ctrl.inspect()
    assert status.latest_commit_sha == result.commit_sha
    assert status.latest_commit_message == "Add documentation"


def test_git_controller_aborts_commit_on_secret_detection(temp_git_repo: Path):
    config = KanomanConfig(git_dry_run=False)
    ctrl = GitController(
        workspace_root=temp_git_repo,
        allowed_remote="https://github.com/qomaruddindjamal/kanoman.git",
        config=config,
    )
    leak_file = temp_git_repo / "leak.env"
    dummy_token = "gh" + "o_" + ("a" * 25)
    leak_file.write_text(f"GITHUB_TOKEN={dummy_token}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Secret scan failed! Aborting commit"):
        ctrl.safe_commit(["leak.env"], "Accidental leak commit", dry_run=False)

    # Ensure file was unstaged and not committed
    status = ctrl.inspect()
    assert status.latest_commit_sha is None
    assert "leak.env" not in status.staged_files
