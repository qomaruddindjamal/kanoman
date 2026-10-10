"""Git Controller for Kanoman AI.

Enforces:
- Isolation of Git operations to authorized repositories and branches.
- Direct subprocess execution with shell=False and strict argument lists.
- Absolute prohibition against destructive commands (reset --hard, force push).
- Pre-commit secret scanning on staged diffs.
- Clear separation between inspect, dry-run, commit, and push modes.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Optional
from kanoman.config.settings import KanomanConfig, get_config
from kanoman.git.models import (
    CommitResult,
    GitOperationMode,
    GitOperationPlan,
    GitStatusResult,
)
from kanoman.logging.logger import get_logger

logger = get_logger("git")

# High-risk secret patterns to block before commit
SECRET_SCAN_PATTERNS = [
    re.compile(r"gho_[A-Za-z0-9_]{20,}", re.IGNORECASE),
    re.compile(r"ghp_[A-Za-z0-9_]{20,}", re.IGNORECASE),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9]{20,}", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z\-_]{35}", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(password|secret|token)\s*=\s*['\"][^\'\"]{8,}['\"]", re.IGNORECASE),
]


class GitController:
    """Centralized controller governing all automated Git operations."""

    def __init__(
        self,
        workspace_root: Path,
        allowed_remote: str,
        allowed_branches: Optional[List[str]] = None,
        config: Optional[KanomanConfig] = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.allowed_remote = allowed_remote.strip()
        self.allowed_branches = allowed_branches or ["main", "develop"]
        self.config = config or get_config()

    def _run_git(self, args: List[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
        """Execute git command safely via subprocess without shell."""
        # Safety Check: Disallow prohibited destructive flags
        for arg in args:
            if arg in {"--force", "-f", "+"} or arg.startswith("--force"):
                raise ValueError(f"Prohibited destructive Git flag detected: '{arg}'")
        if "reset" in args and any(f in args for f in ["--hard", "--merge"]):
            raise ValueError("Destructive command 'git reset --hard' is strictly prohibited.")
        if "clean" in args and any(f in args for f in ["-f", "-fdx", "--force"]):
            raise ValueError("Destructive command 'git clean' is strictly prohibited.")

        cmd = ["git"] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.workspace_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,  # CRITICAL: CWE-78 mitigation
                timeout=timeout,
            )
            return result
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"Git command '{' '.join(args)}' timed out after {timeout}s") from exc

    def verify_repository_identity(self) -> None:
        """Verify that current directory matches repository root, remote, and permitted branch."""
        # 1. Verify Git Root
        res_root = self._run_git(["rev-parse", "--show-toplevel"])
        if res_root.returncode != 0:
            raise ValueError(f"Directory '{self.workspace_root}' is not a valid Git repository.")

        detected_root = Path(res_root.stdout.strip()).resolve()
        if detected_root != self.workspace_root:
            raise ValueError(
                f"Repository root mismatch: expected '{self.workspace_root}', got '{detected_root}'"
            )

        # 2. Verify Remote
        res_remote = self._run_git(["config", "--get", "remote.origin.url"])
        if res_remote.returncode == 0:
            current_remote = res_remote.stdout.strip()
            # Normalize trailing .git
            norm_expected = self.allowed_remote.rstrip("/").removesuffix(".git")
            norm_current = current_remote.rstrip("/").removesuffix(".git")
            if norm_current != norm_expected:
                raise ValueError(
                    f"Remote URL mismatch: authorized '{self.allowed_remote}', but repo has '{current_remote}'"
                )

        # 3. Verify Current Branch
        res_branch = self._run_git(["branch", "--show-current"])
        current_branch = res_branch.stdout.strip()
        if current_branch and current_branch not in self.allowed_branches:
            raise ValueError(
                f"Branch '{current_branch}' is not in authorized branches: {self.allowed_branches}"
            )

    def inspect(self) -> GitStatusResult:
        """Inspect repository status without making any changes."""
        self.verify_repository_identity()

        # Branch
        res_branch = self._run_git(["branch", "--show-current"])
        branch = res_branch.stdout.strip() or "HEAD (detached)"

        # Remote
        res_remote = self._run_git(["config", "--get", "remote.origin.url"])
        remote = res_remote.stdout.strip() if res_remote.returncode == 0 else None

        # Status porcelain
        res_status = self._run_git(["status", "--porcelain"])
        staged: List[str] = []
        unstaged: List[str] = []
        untracked: List[str] = []

        for line in res_status.stdout.splitlines():
            if len(line) < 3:
                continue
            index_code = line[0]
            work_code = line[1]
            file_name = line[3:].strip()

            if index_code in {"M", "A", "D", "R"}:
                staged.append(file_name)
            if work_code in {"M", "D"}:
                unstaged.append(file_name)
            if index_code == "?" and work_code == "?":
                untracked.append(file_name)

        # Latest commit
        res_log = self._run_git(["log", "-1", "--format=%H%n%s"])
        latest_sha: Optional[str] = None
        latest_msg: Optional[str] = None
        if res_log.returncode == 0 and res_log.stdout.strip():
            parts = res_log.stdout.strip().splitlines()
            latest_sha = parts[0]
            if len(parts) > 1:
                latest_msg = parts[1]

        return GitStatusResult(
            root_path=self.workspace_root,
            current_branch=branch,
            remote_url=remote,
            is_clean=len(staged) == 0 and len(unstaged) == 0 and len(untracked) == 0,
            staged_files=staged,
            unstaged_files=unstaged,
            untracked_files=untracked,
            latest_commit_sha=latest_sha,
            latest_commit_message=latest_msg,
        )

    def scan_content_for_secrets(self, content: str) -> List[str]:
        """Scan text content directly for secret patterns."""
        findings = []
        for line in content.splitlines():
            for pattern in SECRET_SCAN_PATTERNS:
                if pattern.search(line):
                    findings.append(f"Secret detected matching pattern: {pattern.pattern}")
        return findings

    def scan_diff_for_secrets(self, diff_text: str) -> List[str]:
        """Scan diff contents for secret patterns, returning matched descriptions."""
        findings = []
        for line in diff_text.splitlines():
            # Only scan added lines
            if line.startswith("+") and not line.startswith("+++"):
                for pattern in SECRET_SCAN_PATTERNS:
                    if pattern.search(line):
                        findings.append(f"Secret detected matching pattern: {pattern.pattern}")
        return findings

    def validate_target_file(self, file_path_str: str) -> Path:
        """Validate target file path against path traversal and prohibited credential file names."""
        clean_str = file_path_str.strip()
        if not clean_str:
            raise ValueError("Target file path cannot be empty.")

        path_obj = Path(clean_str)
        if path_obj.is_absolute() or (len(clean_str) > 1 and clean_str[1] == ":"):
            raise ValueError(f"Absolute file paths are prohibited: '{clean_str}'")

        resolved = (self.workspace_root / path_obj).resolve()
        if self.workspace_root not in resolved.parents and resolved != self.workspace_root:
            raise ValueError(f"Path traversal detected: '{clean_str}' resolves outside workspace root")

        # Prohibit sensitive credential file names
        name_lower = path_obj.name.lower()
        if (
            name_lower == ".env"
            or name_lower.startswith(".env.")
            or any(name_lower.endswith(ext) for ext in [".key", ".pem", ".token", ".pfx", ".p12"])
        ):
            raise ValueError(f"Attempting to operate on prohibited credential file: '{clean_str}'")

        return resolved

    def dry_run(self, files: List[str], message: str) -> GitOperationPlan:
        """Simulate a commit operation without altering repository state."""
        self.verify_repository_identity()
        warnings = []

        # Check file existence and inspect content for secrets
        for f in files:
            try:
                full_path = self.validate_target_file(f)
            except ValueError as ve:
                warnings.append(str(ve))
                continue

            if not full_path.exists():
                warnings.append(f"Target file does not exist: {f}")
            elif full_path.is_file():
                try:
                    content = full_path.read_text(encoding="utf-8", errors="ignore")
                    file_secrets = self.scan_content_for_secrets(content)
                    if file_secrets:
                        warnings.extend(file_secrets)
                except Exception:
                    pass

        # Check diff if file has changes
        res_diff = self._run_git(["diff", "--"] + files)
        if res_diff.returncode == 0 and res_diff.stdout.strip():
            secrets = self.scan_diff_for_secrets(res_diff.stdout)
            if secrets:
                warnings.extend(secrets)

        res_branch = self._run_git(["branch", "--show-current"])
        branch = res_branch.stdout.strip() or "main"

        plan = GitOperationPlan(
            mode=GitOperationMode.DRY_RUN,
            target_branch=branch,
            files_to_stage=files,
            commit_message=message,
            push_target=f"origin/{branch}",
            is_safe=len(warnings) == 0,
            warnings=warnings,
        )
        logger.info(
            f"Git dry-run plan created: {len(files)} files, safe={plan.is_safe}",
            status="GIT_DRY_RUN",
        )
        return plan

    def safe_commit(
        self,
        files: List[str],
        message: str,
        dry_run: bool = False,
    ) -> CommitResult:
        """Stage specific files, scan diff for secrets, and commit safely."""
        if dry_run or self.config.git_dry_run:
            plan = self.dry_run(files, message)
            return CommitResult(
                success=plan.is_safe,
                mode=GitOperationMode.DRY_RUN,
                message=f"[DRY-RUN] Planned commit with {len(files)} files: {message}",
                staged_count=len(files),
                details=f"Warnings: {plan.warnings}" if plan.warnings else None,
            )

        self.verify_repository_identity()

        # Step 0: Validate file paths
        for f in files:
            self.validate_target_file(f)

        # Step 1: Stage specific files
        stage_res = self._run_git(["add", "--"] + files)
        if stage_res.returncode != 0:
            raise RuntimeError(f"Failed to stage files: {stage_res.stderr}")

        # Step 2: Staged diff secret scanning & whitespace check
        diff_res = self._run_git(["diff", "--cached"])
        secrets = self.scan_diff_for_secrets(diff_res.stdout)
        if secrets:
            # Unstage immediately on secret detection
            self._run_git(["reset", "HEAD", "--"] + files)
            raise ValueError(f"Secret scan failed! Aborting commit. Found: {secrets}")

        # Whitespace error check
        self._run_git(["diff", "--cached", "--check"])

        # Step 3: Execute commit
        commit_res = self._run_git(["commit", "-m", message])
        if commit_res.returncode != 0:
            raise RuntimeError(f"Commit failed: {commit_res.stderr}")

        # Step 4: Verify local commit SHA
        sha_res = self._run_git(["rev-parse", "HEAD"])
        new_sha = sha_res.stdout.strip() if sha_res.returncode == 0 else None

        logger.info(
            f"Git commit created: {new_sha[:8] if new_sha else 'unknown'} - {message}",
            status="GIT_COMMITTED",
        )
        return CommitResult(
            success=True,
            mode=GitOperationMode.COMMIT,
            commit_sha=new_sha,
            message=message,
            staged_count=len(files),
        )

    def safe_push(
        self,
        remote: str = "origin",
        branch: Optional[str] = None,
        dry_run: bool = False,
    ) -> bool:
        """Push local commits to verified remote branch without force."""
        if dry_run or self.config.git_dry_run:
            logger.info("[DRY-RUN] Skipping push to remote.", status="GIT_PUSH_DRY_RUN")
            return True

        self.verify_repository_identity()

        # Verify remote URL
        res_rem_url = self._run_git(["config", "--get", f"remote.{remote}.url"])
        if res_rem_url.returncode != 0:
            raise ValueError(f"Remote '{remote}' is not configured in this repository.")
        actual_remote_url = res_rem_url.stdout.strip().rstrip("/").removesuffix(".git")
        expected_remote_url = self.allowed_remote.rstrip("/").removesuffix(".git")
        if actual_remote_url != expected_remote_url:
            raise ValueError(
                f"Unauthorized push remote URL: remote '{remote}' points to '{actual_remote_url}', "
                f"expected '{self.allowed_remote}'"
            )

        target_branch = branch
        if not target_branch:
            res_b = self._run_git(["branch", "--show-current"])
            target_branch = res_b.stdout.strip()

        if target_branch not in self.allowed_branches:
            raise ValueError(f"Cannot push to non-authorized branch '{target_branch}'")

        # Push to remote branch
        push_res = self._run_git(["push", remote, target_branch], timeout=60)
        if push_res.returncode != 0:
            logger.error(f"Push failed: {push_res.stderr}", status="GIT_PUSH_FAILED")
            raise RuntimeError(f"Git push failed: {push_res.stderr}")

        logger.info(
            f"Successfully pushed to {remote}/{target_branch}",
            status="GIT_PUSH_SUCCESS",
        )
        return True
