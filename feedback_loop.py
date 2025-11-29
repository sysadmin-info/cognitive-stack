#!/usr/bin/env python3
"""Feedback loop: iterate code fixes until SonarQube passes.

This module orchestrates the cycle:
1. Run linters (ruff, ansible-lint, tflint)
2. Run SonarQube analysis
3. If issues found → send to LLM council for fixes
4. Apply fixes and repeat until clean or max iterations
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from providers import BaseProvider, Response
    from sonar_client import SonarClient, SonarReport

logger = logging.getLogger(__name__)


# Language-specific linter configurations
LINTER_CONFIGS = {
    "python": {
        "linters": ["ruff check --fix", "ruff format"],
        "extensions": [".py"],
    },
    "ansible": {
        "linters": ["ansible-lint --fix"],
        "extensions": [".yml", ".yaml"],
        "markers": ["tasks/", "handlers/", "roles/"],
    },
    "terraform": {
        "linters": ["terraform fmt -recursive", "tflint"],
        "extensions": [".tf"],
    },
}


@dataclass
class LinterResult:
    """Result from running a linter."""
    
    linter: str
    passed: bool
    output: str = ""
    fixed_count: int = 0


@dataclass
class IterationResult:
    """Result from one iteration of the feedback loop."""
    
    iteration: int
    linter_results: list[LinterResult] = field(default_factory=list)
    sonar_report: SonarReport | None = None
    fixes_applied: bool = False
    error: str | None = None
    
    @property
    def passed(self) -> bool:
        """Check if iteration passed all checks."""
        linters_ok = all(r.passed for r in self.linter_results)
        sonar_ok = self.sonar_report is None or self.sonar_report.passed
        return linters_ok and sonar_ok


@dataclass
class FeedbackLoopResult:
    """Final result of the feedback loop."""
    
    iterations: list[IterationResult] = field(default_factory=list)
    final_passed: bool = False
    total_issues_fixed: int = 0
    
    def format_summary(self) -> str:
        """Format summary for display."""
        status = "✅ PASSED" if self.final_passed else "❌ FAILED"
        lines = [
            f"## Feedback Loop {status}",
            f"Iterations: {len(self.iterations)}",
            f"Total issues fixed: {self.total_issues_fixed}",
            ""
        ]
        
        for result in self.iterations:
            iter_status = "✅" if result.passed else "❌"
            lines.append(f"### Iteration {result.iteration} {iter_status}")
            
            for lr in result.linter_results:
                lr_status = "✅" if lr.passed else "❌"
                lines.append(f"  - {lr.linter}: {lr_status}")
            
            if result.sonar_report:
                lines.append(f"  - SonarQube: {result.sonar_report.format_summary()}")
            
            if result.error:
                lines.append(f"  - Error: {result.error}")
            
            lines.append("")
        
        return "\n".join(lines)


class FeedbackLoop:
    """Orchestrates iterative code fixes until quality gates pass."""
    
    def __init__(
        self,
        sonar_client: SonarClient,
        llm_provider: BaseProvider,
        project_dir: str | Path,
        project_key: str,
        language: str = "python",
        max_iterations: int = 5,
    ):
        self.sonar = sonar_client
        self.llm = llm_provider
        self.project_dir = Path(project_dir)
        self.project_key = project_key
        self.language = language
        self.max_iterations = max_iterations
        self.linter_config = LINTER_CONFIGS.get(language, LINTER_CONFIGS["python"])
    
    async def run(self) -> FeedbackLoopResult:
        """Run the feedback loop until clean or max iterations."""
        result = FeedbackLoopResult()
        
        for i in range(1, self.max_iterations + 1):
            logger.info(f"=== Iteration {i}/{self.max_iterations} ===")
            
            iteration = await self._run_iteration(i)
            result.iterations.append(iteration)
            
            if iteration.passed:
                result.final_passed = True
                logger.info(f"✅ All checks passed on iteration {i}")
                break
            
            if iteration.error:
                logger.error(f"Error in iteration {i}: {iteration.error}")
                break
            
            # Count fixed issues
            if iteration.sonar_report:
                prev_issues = (
                    result.iterations[-2].sonar_report.issues 
                    if len(result.iterations) > 1 and result.iterations[-2].sonar_report
                    else []
                )
                current_issues = iteration.sonar_report.issues
                result.total_issues_fixed += max(0, len(prev_issues) - len(current_issues))
        
        return result
    
    async def _run_iteration(self, iteration_num: int) -> IterationResult:
        """Run one iteration of checks and fixes."""
        result = IterationResult(iteration=iteration_num)
        
        try:
            # 1. Run linters (with auto-fix where possible)
            result.linter_results = await self._run_linters()
            
            # 2. Run SonarQube analysis
            result.sonar_report = await self.sonar.scan_and_wait(
                project_dir=self.project_dir,
                project_key=self.project_key
            )
            
            # 3. If issues found, ask LLM to fix
            if not result.passed:
                result.fixes_applied = await self._apply_llm_fixes(
                    result.linter_results,
                    result.sonar_report
                )
        
        except Exception as e:
            result.error = str(e)
            logger.exception(f"Error in iteration {iteration_num}")
        
        return result
    
    async def _run_linters(self) -> list[LinterResult]:
        """Run all configured linters."""
        results = []
        
        for linter_cmd in self.linter_config["linters"]:
            result = await self._run_single_linter(linter_cmd)
            results.append(result)
        
        return results
    
    async def _run_single_linter(self, linter_cmd: str) -> LinterResult:
        """Run a single linter command."""
        linter_name = linter_cmd.split()[0]
        
        # Check if linter is available
        if not shutil.which(linter_name):
            logger.warning(f"Linter not found: {linter_name}")
            return LinterResult(
                linter=linter_name,
                passed=True,  # Skip if not installed
                output=f"{linter_name} not installed, skipping"
            )
        
        try:
            proc = await asyncio.create_subprocess_shell(
                linter_cmd,
                cwd=self.project_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode()
            
            return LinterResult(
                linter=linter_name,
                passed=(proc.returncode == 0),
                output=output
            )
        
        except Exception as e:
            return LinterResult(
                linter=linter_name,
                passed=False,
                output=str(e)
            )
    
    def _build_fix_context(
        self,
        linter_results: list[LinterResult],
        sonar_report: SonarReport | None
    ) -> str:
        """Build context string for LLM fix request."""
        context_parts = ["Fix the following issues in the code:\n"]
        
        # Add linter issues
        for lr in linter_results:
            if not lr.passed:
                context_parts.append(f"## {lr.linter} issues:\n{lr.output}\n")
        
        # Add SonarQube issues
        if sonar_report and not sonar_report.passed:
            context_parts.append(sonar_report.format_for_llm())
        
        return "\n".join(context_parts)
    
    async def _fix_single_file(
        self,
        file_path: str,
        context: str
    ) -> bool:
        """Fix a single file using LLM."""
        full_path = self.project_dir / file_path
        
        if not full_path.exists():
            return False
        
        original_content = full_path.read_text()
        
        prompt = f"""{context}

## File to fix: {file_path}

```{self._get_file_extension(file_path)}
{original_content}
```

Provide the complete fixed file content. Only output the code, no explanations.
Wrap the code in triple backticks with the language identifier."""
        
        messages = [{"role": "user", "content": prompt}]
        response = await self.llm.complete(messages)
        
        if not response.ok or not response.content:
            return False
        
        fixed_content = self._extract_code_from_response(response.content)
        if not fixed_content or fixed_content == original_content:
            return False
        
        # Backup original and write fixed content
        backup_path = full_path.with_suffix(full_path.suffix + ".bak")
        backup_path.write_text(original_content)
        full_path.write_text(fixed_content)
        logger.info(f"Applied fixes to {file_path}")
        return True
    
    async def _apply_llm_fixes(
        self,
        linter_results: list[LinterResult],
        sonar_report: SonarReport | None
    ) -> bool:
        """Ask LLM to fix issues and apply changes."""
        files_to_fix = self._get_files_with_issues(linter_results, sonar_report)
        
        if not files_to_fix:
            logger.warning("No files identified for fixing")
            return False
        
        context = self._build_fix_context(linter_results, sonar_report)
        
        for file_path in files_to_fix:
            await self._fix_single_file(file_path, context)
        
        return True
    
    def _extract_files_from_linter_output(self, lr: LinterResult) -> set[str]:
        """Extract file paths from linter output."""
        files = set()
        if lr.passed or not lr.output:
            return files
        
        extensions = tuple(self.linter_config.get("extensions", [".py"]))
        for line in lr.output.split("\n"):
            if ":" not in line or line.startswith(" "):
                continue
            potential_file = line.split(":")[0].strip()
            if potential_file.endswith(extensions):
                files.add(potential_file)
        return files
    
    def _get_files_with_issues(
        self,
        linter_results: list[LinterResult],
        sonar_report: SonarReport | None
    ) -> list[str]:
        """Extract list of files that need fixing."""
        files = set()
        
        # From SonarQube
        if sonar_report:
            files.update(issue.file for issue in sonar_report.issues)
        
        # From linter output
        for lr in linter_results:
            files.update(self._extract_files_from_linter_output(lr))
        
        return list(files)
    
    def _get_file_extension(self, file_path: str) -> str:
        """Get language identifier for code blocks."""
        ext = Path(file_path).suffix.lower()
        mapping = {
            ".py": "python",
            ".tf": "terraform",
            ".yml": "yaml",
            ".yaml": "yaml",
            ".sh": "bash",
            ".js": "javascript",
            ".ts": "typescript",
        }
        return mapping.get(ext, "")
    
    def _extract_code_from_response(self, response: str) -> str | None:
        """Extract code block from LLM response."""
        lines = response.split("\n")
        in_code_block = False
        code_lines = []
        
        for line in lines:
            if line.startswith("```") and not in_code_block:
                in_code_block = True
            elif line.startswith("```") and in_code_block:
                break
            elif in_code_block:
                code_lines.append(line)
        
        if code_lines:
            return "\n".join(code_lines)
        
        return None


async def run_feedback_loop(
    project_dir: str,
    project_key: str,
    language: str = "python",
    max_iterations: int = 5,
    sonar_url: str = "http://localhost:9000",
    sonar_token: str | None = None,
) -> FeedbackLoopResult:
    """Convenience function to run feedback loop.
    
    Args:
        project_dir: Path to project directory
        project_key: SonarQube project key
        language: Programming language (python, ansible, terraform)
        max_iterations: Maximum fix iterations
        sonar_url: SonarQube server URL
        sonar_token: SonarQube authentication token
        
    Returns:
        FeedbackLoopResult with all iteration details
    """
    from sonar_client import SonarClient
    from providers import create_provider, load_configs
    
    sonar = SonarClient(
        base_url=sonar_url,
        token=sonar_token or os.getenv("SONAR_TOKEN")
    )
    
    # Load provider config and create LLM provider
    configs = load_configs()
    provider_configs = configs.get("providers", {})
    
    # Use first available enabled provider
    llm = None
    for provider_name in ["anthropic", "openai", "google"]:
        if provider_name in provider_configs:
            provider_cfg = provider_configs[provider_name]
            if provider_cfg.get("enabled", False):
                llm = create_provider(provider_name, provider_cfg)
                break
    
    if llm is None:
        raise RuntimeError("No enabled LLM provider found in config")
    
    loop = FeedbackLoop(
        sonar_client=sonar,
        llm_provider=llm,
        project_dir=project_dir,
        project_key=project_key,
        language=language,
        max_iterations=max_iterations
    )
    
    return await loop.run()


# CLI entry point
async def main():
    """CLI entry point."""
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    project_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    project_key = sys.argv[2] if len(sys.argv) > 2 else "cognitive-stack"
    language = sys.argv[3] if len(sys.argv) > 3 else "python"
    
    result = await run_feedback_loop(
        project_dir=project_dir,
        project_key=project_key,
        language=language
    )
    
    print(result.format_summary())
    sys.exit(0 if result.final_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
