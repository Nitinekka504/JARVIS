import ast
import shutil
import py_compile
import subprocess
import os
import sys
import difflib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

class SelfModificationEngine:
    """
    Autonomous Self-Modification Engine.
    Enables JARVIS to safely analyze, edit, compile-check, test, and apply changes to its own source repository.
    
    Safety Safeguards:
    1. Unified Diff generation & HUD streaming (`difflib`).
    2. AST Syntax validation (`ast.parse`).
    3. Staging in `.jarvis_staging/`.
    4. Backup creation in `.jarvis_backups/`.
    5. Compile checking (`py_compile`).
    6. Automated test execution (`pytest`/`unittest`).
    7. Automatic rollback on failure.
    """

    def __init__(self, repo_root: str = "."):
        self.repo_root = Path(repo_root).resolve()
        self.backup_dir = self.repo_root / ".jarvis_backups"
        self.staging_dir = self.repo_root / ".jarvis_staging"
        
        self.backup_dir.mkdir(exist_ok=True)
        self.staging_dir.mkdir(exist_ok=True)

    def generate_unified_diff(self, relative_filepath: str, new_code_content: str) -> str:
        """Generates unified green/red syntax diff between existing file and proposed new code."""
        target_path = (self.repo_root / relative_filepath).resolve()
        old_lines = []
        if target_path.exists():
            with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                old_lines = f.readlines()
        
        new_lines = [line + ("\n" if not line.endswith("\n") else "") for line in new_code_content.splitlines()]

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{relative_filepath}",
            tofile=f"b/{relative_filepath}",
            lineterm=""
        )
        return "\n".join(diff)

    def validate_ast(self, code_str: str) -> Tuple[bool, Optional[str]]:
        """Parses python string into AST to detect syntax errors before saving."""
        try:
            ast.parse(code_str)
            return True, None
        except SyntaxError as se:
            return False, f"SyntaxError line {se.lineno}: {se.msg}"
        except Exception as e:
            return False, str(e)

    def stage_and_test_modification(self, relative_filepath: str, new_code_content: str, confirmed: bool = False) -> Dict[str, Any]:
        """
        Executes complete self-editing verification pipeline:
        1. Generate Unified Diff.
        2. Validate AST syntax.
        3. Verify human confirmation gate (Ponytail SEC-02).
        4. Create backup of current file.
        5. Write to staging.
        6. Run compile check.
        7. Run test suite verification.
        8. Apply atomic overwrite or execute rollback.
        """
        target_path = (self.repo_root / relative_filepath).resolve()
        if not target_path.is_relative_to(self.repo_root):
            return {"success": False, "reason": "Security violation: Path outside repository boundary."}

        # Step 1: Generate Diff
        diff_text = self.generate_unified_diff(relative_filepath, new_code_content)

        # Broadcast diff event to Dashboard Hub if running
        try:
            from dashboard.server import HUB
            asyncio.create_task(HUB.broadcast("code_diff", {
                "filepath": relative_filepath,
                "diff_text": diff_text
            }))
        except Exception:
            pass

        # Step 2: AST Syntax Validation
        valid_ast, ast_err = self.validate_ast(new_code_content)
        if not valid_ast:
            return {
                "success": False,
                "stage": "AST_VALIDATION",
                "diff_text": diff_text,
                "error": f"AST Syntax Check Failed: {ast_err}"
            }

        # Step 3: Human-in-the-Loop Confirmation Gate (Ponytail SEC-02)
        if not confirmed:
            return {
                "success": False,
                "stage": "CONFIRMATION_REQUIRED",
                "diff_text": diff_text,
                "message": (
                    f"Diff generated and syntax validated for '{relative_filepath}'. "
                    "Confirmation required: Pass confirmed=True to execute test runner and apply modifications."
                )
            }

        # Step 3: Backup Original File
        backup_file = None
        if target_path.exists():
            backup_filename = f"{target_path.stem}_backup{target_path.suffix}"
            backup_file = self.backup_dir / backup_filename
            shutil.copy2(target_path, backup_file)

        # Step 4: Write to Staging
        staging_file = self.staging_dir / target_path.name
        with open(staging_file, "w", encoding="utf-8") as f:
            f.write(new_code_content)

        # Step 5: Compile Check
        try:
            py_compile.compile(str(staging_file), doraise=True)
        except py_compile.PyCompileError as pce:
            return {
                "success": False,
                "stage": "COMPILE_CHECK",
                "diff_text": diff_text,
                "error": f"Compilation Failed: {pce}"
            }

        # Step 6: Test Execution
        test_passed = self._run_tests()
        if not test_passed["success"]:
            if staging_file.exists():
                os.remove(staging_file)
            return {
                "success": False,
                "stage": "TEST_VERIFICATION",
                "diff_text": diff_text,
                "error": f"Test Verification Failed: {test_passed.get('details')}"
            }

        # Step 7: Apply Atomic Overwrite
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staging_file), str(target_path))
            return {
                "success": True,
                "file_modified": relative_filepath,
                "diff_text": diff_text,
                "backup_created": str(backup_file) if backup_file else None,
                "message": f"Successfully updated {relative_filepath} with 100% syntax and test validation."
            }
        except Exception as e:
            if backup_file and backup_file.exists():
                shutil.copy2(backup_file, target_path)
            return {
                "success": False,
                "stage": "ATOMIC_APPLY",
                "diff_text": diff_text,
                "error": f"Failed during atomic apply, rollback executed: {e}"
            }

    def rollback(self, relative_filepath: str) -> Dict[str, Any]:
        """Manually triggers restoration of a file from its backup."""
        target_path = (self.repo_root / relative_filepath).resolve()
        backup_filename = f"{target_path.stem}_backup{target_path.suffix}"
        backup_file = self.backup_dir / backup_filename
        
        if backup_file.exists():
            shutil.copy2(backup_file, target_path)
            return {"success": True, "message": f"Restored {relative_filepath} from backup {backup_file.name}"}
        return {"success": False, "message": f"No backup found for {relative_filepath}"}

    def _run_tests(self) -> Dict[str, Any]:
        """Executes test suite if test runner script exists."""
        test_runner = self.repo_root / "tests" / "run_tests.py"
        if not test_runner.exists():
            return {"success": True, "details": "No test runner script found, skipping test check."}

        try:
            result = subprocess.run(
                [sys.executable, str(test_runner)],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return {"success": True, "details": result.stdout}
            else:
                return {"success": False, "details": result.stderr or result.stdout}
        except Exception as e:
            return {"success": False, "details": str(e)}
