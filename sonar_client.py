#!/usr/bin/env python3
"""SonarQube API client with wait-for-results and LLM-friendly formatting."""

from __future__ import annotations

import asyncio
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SonarIssue:
    """Single SonarQube issue."""
    
    rule: str
    severity: str
    message: str
    file: str
    line: int
    effort: str = ""
    
    def format(self) -> str:
        """Format single issue as string."""
        return f"[{self.severity}] {self.file}:{self.line} - {self.message} (rule: {self.rule})"


@dataclass
class SonarReport:
    """SonarQube analysis report."""
    
    project_key: str
    issues: list[SonarIssue] = field(default_factory=list)
    
    @property
    def passed(self) -> bool:
        """Check if no issues found."""
        return len(self.issues) == 0
    
    @property
    def critical_count(self) -> int:
        """Count critical and blocker issues."""
        return sum(1 for i in self.issues if i.severity in ("CRITICAL", "BLOCKER"))
    
    @property
    def major_count(self) -> int:
        """Count major issues."""
        return sum(1 for i in self.issues if i.severity == "MAJOR")
    
    def format_for_llm(self) -> str:
        """Format issues for LLM to understand and fix."""
        if self.passed:
            return "✅ No issues found. Code is clean."
        
        lines = [
            f"❌ Found {len(self.issues)} issues "
            f"({self.critical_count} critical, {self.major_count} major):",
            ""
        ]
        
        # Group by file
        by_file: dict[str, list[SonarIssue]] = {}
        for issue in self.issues:
            by_file.setdefault(issue.file, []).append(issue)
        
        for file_path, file_issues in sorted(by_file.items()):
            lines.append(f"## {file_path}")
            # Sort by line number
            for i, issue in enumerate(sorted(file_issues, key=lambda x: x.line), 1):
                lines.append(f"{i}. Line {issue.line}: [{issue.severity}] {issue.message}")
                lines.append(f"   Rule: {issue.rule}")
            lines.append("")
        
        lines.append("Please fix these issues and ensure the code follows best practices.")
        return "\n".join(lines)
    
    def format_summary(self) -> str:
        """Short summary for logging."""
        if self.passed:
            return "✅ Clean"
        return f"❌ {len(self.issues)} issues ({self.critical_count} critical)"


class SonarClient:
    """SonarQube API client."""
    
    def __init__(
        self, 
        base_url: str = "http://localhost:9000",
        token: str | None = None
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._auth = (token, "") if token else None
    
    async def scan_and_wait(
        self,
        project_dir: str | Path,
        project_key: str,
        timeout: int = 300,
        poll_interval: int = 2
    ) -> SonarReport:
        """Run sonar-scanner and wait for results.
        
        Args:
            project_dir: Directory containing sonar-project.properties
            project_key: SonarQube project key
            timeout: Max seconds to wait for analysis
            poll_interval: Seconds between status checks
            
        Returns:
            SonarReport with all unresolved issues
        """
        project_dir = Path(project_dir)
        
        # 1. Run scanner
        task_id = await self._run_scanner(project_dir)
        logger.info(f"Scan submitted, task ID: {task_id}")
        
        # 2. Wait for completion
        await self._wait_for_task(task_id, timeout, poll_interval)
        logger.info("Analysis complete")
        
        # 3. Fetch issues
        return await self.get_issues(project_key)
    
    async def _run_scanner(self, project_dir: Path) -> str:
        """Run sonar-scanner and extract task ID."""
        proc = await asyncio.create_subprocess_exec(
            "sonar-scanner",
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode()
        
        if proc.returncode != 0:
            raise RuntimeError(f"sonar-scanner failed:\n{output}")
        
        # Extract task ID from output
        for line in output.split("\n"):
            if "task?id=" in line:
                # Format: ...http://localhost:9000/api/ce/task?id=XXXXX
                task_id = line.split("task?id=")[1].split()[0].strip()
                return task_id
        
        raise RuntimeError("Could not find task ID in scanner output")
    
    async def _wait_for_task(
        self, 
        task_id: str, 
        timeout: int,
        poll_interval: int
    ) -> None:
        """Poll until analysis task completes."""
        async with httpx.AsyncClient(auth=self._auth, timeout=30) as client:
            start = time.time()
            
            while time.time() - start < timeout:
                resp = await client.get(
                    f"{self.base_url}/api/ce/task",
                    params={"id": task_id}
                )
                resp.raise_for_status()
                
                status = resp.json()["task"]["status"]
                
                if status == "SUCCESS":
                    return
                elif status in ("FAILED", "CANCELED"):
                    raise RuntimeError(f"SonarQube analysis {status}")
                
                # Still pending/in progress
                elapsed = int(time.time() - start)
                logger.debug(f"Analysis in progress... ({elapsed}s)")
                await asyncio.sleep(poll_interval)
            
            raise TimeoutError(f"SonarQube analysis timeout after {timeout}s")
    
    async def get_issues(
        self, 
        project_key: str,
        resolved: bool = False,
        severities: list[str] | None = None
    ) -> SonarReport:
        """Fetch issues from SonarQube.
        
        Args:
            project_key: SonarQube project key
            resolved: Include resolved issues
            severities: Filter by severities (BLOCKER, CRITICAL, MAJOR, MINOR, INFO)
            
        Returns:
            SonarReport with matching issues
        """
        async with httpx.AsyncClient(auth=self._auth, timeout=30) as client:
            issues: list[SonarIssue] = []
            page = 1
            page_size = 500
            
            while True:
                params: dict = {
                    "componentKeys": project_key,
                    "resolved": str(resolved).lower(),
                    "ps": page_size,
                    "p": page
                }
                
                if severities:
                    params["severities"] = ",".join(severities)
                
                resp = await client.get(
                    f"{self.base_url}/api/issues/search",
                    params=params
                )
                resp.raise_for_status()
                data = resp.json()
                
                for item in data.get("issues", []):
                    # Extract file path from component
                    component = item.get("component", "")
                    file_path = component.split(":")[-1] if ":" in component else component
                    
                    issues.append(SonarIssue(
                        rule=item.get("rule", ""),
                        severity=item.get("severity", "INFO"),
                        message=item.get("message", ""),
                        file=file_path,
                        line=item.get("line", 0) or item.get("textRange", {}).get("startLine", 0),
                        effort=item.get("effort", "")
                    ))
                
                # Check if we have all issues
                total = data.get("total", 0)
                if len(issues) >= total:
                    break
                page += 1
            
            return SonarReport(project_key=project_key, issues=issues)
    
    async def get_project_status(self, project_key: str) -> dict:
        """Get project quality gate status."""
        async with httpx.AsyncClient(auth=self._auth, timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/qualitygates/project_status",
                params={"projectKey": project_key}
            )
            resp.raise_for_status()
            return resp.json()


# CLI usage
async def main():
    """CLI entry point for testing."""
    import os
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    client = SonarClient(
        base_url=os.getenv("SONAR_URL", "http://localhost:9000"),
        token=os.getenv("SONAR_TOKEN")
    )
    
    project_key = sys.argv[1] if len(sys.argv) > 1 else "cognitive-stack"
    
    # Check if --scan flag is passed
    if "--scan" in sys.argv:
        project_dir = sys.argv[2] if len(sys.argv) > 2 else "."
        report = await client.scan_and_wait(
            project_dir=project_dir,
            project_key=project_key
        )
    else:
        report = await client.get_issues(project_key)
    
    print(report.format_for_llm())
    print(f"\nStatus: {report.format_summary()}")
    
    # Exit with error code if issues found
    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
