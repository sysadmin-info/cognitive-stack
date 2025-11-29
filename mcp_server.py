#!/usr/bin/env python3
"""MCP Server for Cognitive Stack.

Exposes LLM Council, Variance Analysis, Debiasing, and SonarQube integration
as MCP tools for use with Claude Code and other MCP-compatible clients.

Usage:
    # Run as stdio server (for Claude Code)
    python mcp_server.py
    
    # Or with uvx
    uvx mcp run cognitive-stack
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP(
    name="cognitive-stack",
    version="1.5.0",
    description="Multi-LLM Council with Variance Analysis and Debiasing"
)

logger = logging.getLogger(__name__)


# ============================================================================
# TOOLS
# ============================================================================

async def _query_single_provider(
    name: str,
    cfg: dict,
    messages: list,
    system: str
) -> Any | None:
    """Query a single provider and return response or None on failure."""
    from providers import create_provider
    
    if not cfg.get("enabled", False):
        return None
    
    try:
        provider = create_provider(name, cfg)
        return await provider.complete(messages, system=system)
    except Exception as e:
        logger.warning(f"Provider {name} failed: {e}")
        return None


def _format_council_responses(responses: list) -> list[str]:
    """Format successful responses for output."""
    output_parts = ["## Council Responses\n"]
    for resp in responses:
        if resp.ok:
            output_parts.append(f"### {resp.provider} ({resp.model})")
            output_parts.append(resp.content)
            output_parts.append("")
    return output_parts


@mcp.tool()
async def council_query(
    query: str,
    providers: str = "anthropic,openai,google",
    expert: str | None = None,
    show_variance: bool = True
) -> str:
    """Query multiple LLM models and get consensus with variance analysis.
    
    Args:
        query: The question or task to send to the council
        providers: Comma-separated list of providers (anthropic,openai,google,ollama,lmstudio)
        expert: Optional expert persona to use (e.g., 'security_expert', 'architect')
        show_variance: Whether to include variance analysis in response
        
    Returns:
        Responses from all models with optional variance analysis
    """
    from providers import create_provider, load_configs
    from analyzers import analyze_variance
    
    configs = load_configs()
    provider_configs = configs.get("providers", {})
    expert_configs = configs.get("experts", {})
    user_model = configs.get("user_model", {})
    
    # Get language preference
    comm_style = user_model.get("communication_style", {})
    language = comm_style.get("preferred_language", "en")
    
    # Parse providers list
    provider_names = [p.strip() for p in providers.split(",")]
    
    # Build system prompt
    system = expert_configs.get(expert, {}).get("system_prompt", "") if expert else ""
    
    # Query each provider
    messages = [{"role": "user", "content": query}]
    responses = []
    
    for name in provider_names:
        cfg = provider_configs.get(name)
        if not cfg:
            continue
        resp = await _query_single_provider(name, cfg, messages, system)
        if resp:
            responses.append(resp)
    
    if not responses:
        return "Error: No providers returned responses"
    
    # Format output
    output_parts = _format_council_responses(responses)
    
    # Add variance analysis
    if show_variance and len(responses) > 1:
        successful = [r for r in responses if r.ok]
        if successful:
            analyzer = create_provider("anthropic", provider_configs.get("anthropic", {}))
            variance = await analyze_variance(successful, analyzer, language)
            output_parts.append(variance.format())
    
    return "\n".join(output_parts)


@mcp.tool()
async def run_debiasing(
    content: str,
    techniques: str = "premortem,counterargs,assumptions",
    context: str = ""
) -> str:
    """Apply debiasing techniques to analyze decisions or plans.
    
    Args:
        content: The decision, plan, or response to analyze
        techniques: Comma-separated techniques (premortem,counterargs,uncertainty,assumptions,reference_class,change_mind)
        context: Optional additional context about the user/situation
        
    Returns:
        Debiasing analysis results
    """
    from providers import create_provider, load_configs
    from analyzers import run_debiasing as _run_debiasing, format_debiasing_results
    
    configs = load_configs()
    provider_configs = configs.get("providers", {})
    user_model = configs.get("user_model", {})
    
    # Get language preference
    comm_style = user_model.get("communication_style", {})
    language = comm_style.get("preferred_language", "en")
    
    # Parse techniques
    technique_list = [t.strip() for t in techniques.split(",")]
    
    # Get first available provider
    provider = None
    for name in ["anthropic", "openai", "google"]:
        if name in provider_configs and provider_configs[name].get("enabled"):
            provider = create_provider(name, provider_configs[name])
            break
    
    if not provider:
        return "Error: No enabled LLM provider found"
    
    results = await _run_debiasing(
        content,
        technique_list,
        provider,
        user_context=context,
        parallel=True,
        language=language
    )
    
    return format_debiasing_results(results, language)


@mcp.tool()
async def devils_advocate(
    code: str,
    language: str = "python",
    focus: str = "security"
) -> str:
    """Security-focused devil's advocate review of code.
    
    Args:
        code: The code to review
        language: Programming language (python, ansible, terraform)
        focus: Review focus (security, performance, maintainability)
        
    Returns:
        Critical analysis of potential issues
    """
    from providers import create_provider, load_configs
    
    configs = load_configs()
    provider_configs = configs.get("providers", {})
    
    prompts = {
        "python": f"""You are a security researcher doing adversarial code review.
Your job is to find vulnerabilities, not to praise the code.

Focus areas for {focus}:
- Injection vulnerabilities (SQL, command, path traversal)
- Insecure deserialization
- Secrets/credentials in code
- Missing input validation
- SSRF, CSRF vulnerabilities
- Insecure cryptography
- Race conditions

Code to review:
```{language}
{code}
```

List ALL potential issues, even minor ones. Be thorough and critical.""",

        "ansible": f"""You are a security auditor reviewing Ansible code.
Your job is to find problems, not to approve the code.

Focus areas for {focus}:
- Hardcoded secrets or credentials
- Privilege escalation risks
- Insecure file permissions
- Missing handlers for failures
- Non-idempotent operations
- Unencrypted sensitive data
- Missing become/sudo controls

Code to review:
```yaml
{code}
```

List ALL potential issues. Be thorough and critical.""",

        "terraform": f"""You are a cloud security architect reviewing Terraform code.
Your job is to find risks, not to approve the infrastructure.

Focus areas for {focus}:
- Overly permissive IAM policies
- Public S3 buckets/storage
- Missing encryption at rest/transit
- Wide security group rules
- Hardcoded credentials
- Missing logging/monitoring
- Excessive blast radius
- Cost optimization issues

Code to review:
```hcl
{code}
```

List ALL potential issues. Be thorough and critical."""
    }
    
    prompt = prompts.get(language, prompts["python"])
    
    # Get first available provider
    provider = None
    for name in ["anthropic", "openai", "google"]:
        if name in provider_configs and provider_configs[name].get("enabled"):
            provider = create_provider(name, provider_configs[name])
            break
    
    if not provider:
        return "Error: No enabled LLM provider found"
    
    messages = [{"role": "user", "content": prompt}]
    response = await provider.complete(messages)
    
    if response.ok:
        return f"## Devil's Advocate Review ({focus})\n\n{response.content}"
    return f"Error: {response.error}"


@mcp.tool()
async def sonar_scan(
    project_dir: str = ".",
    project_key: str | None = None,
    wait: bool = True
) -> str:
    """Run SonarQube analysis and get issues.
    
    Args:
        project_dir: Directory containing sonar-project.properties
        project_key: SonarQube project key (reads from properties if not provided)
        wait: Whether to wait for analysis to complete
        
    Returns:
        SonarQube issues formatted for fixing
    """
    from sonar_client import SonarClient
    
    project_path = Path(project_dir)
    
    # Try to read project key from properties file
    if not project_key:
        props_file = project_path / "sonar-project.properties"
        if props_file.exists():
            for line in props_file.read_text().split("\n"):
                if line.startswith("sonar.projectKey="):
                    project_key = line.split("=", 1)[1].strip()
                    break
    
    if not project_key:
        return "Error: project_key not provided and not found in sonar-project.properties"
    
    client = SonarClient(
        base_url=os.getenv("SONAR_URL", "http://localhost:9000"),
        token=os.getenv("SONAR_TOKEN")
    )
    
    if wait:
        report = await client.scan_and_wait(project_path, project_key)
    else:
        report = await client.get_issues(project_key)
    
    return report.format_for_llm()


@mcp.tool()
async def iterate_until_clean(
    project_dir: str = ".",
    project_key: str | None = None,
    language: str = "python",
    max_iterations: int = 5
) -> str:
    """Run feedback loop to fix code until SonarQube passes.
    
    Args:
        project_dir: Directory containing the code
        project_key: SonarQube project key
        language: Programming language (python, ansible, terraform)
        max_iterations: Maximum fix iterations
        
    Returns:
        Summary of iterations and final status
    """
    from feedback_loop import run_feedback_loop
    
    project_path = Path(project_dir)
    
    # Try to read project key from properties file
    if not project_key:
        props_file = project_path / "sonar-project.properties"
        if props_file.exists():
            for line in props_file.read_text().split("\n"):
                if line.startswith("sonar.projectKey="):
                    project_key = line.split("=", 1)[1].strip()
                    break
    
    if not project_key:
        return "Error: project_key not provided and not found in sonar-project.properties"
    
    result = await run_feedback_loop(
        project_dir=str(project_path),
        project_key=project_key,
        language=language,
        max_iterations=max_iterations,
        sonar_url=os.getenv("SONAR_URL", "http://localhost:9000"),
        sonar_token=os.getenv("SONAR_TOKEN")
    )
    
    return result.format_summary()


@mcp.tool()
async def list_experts() -> str:
    """List available expert personas for council queries.
    
    Returns:
        List of experts with descriptions and triggers
    """
    from providers import load_configs
    
    configs = load_configs()
    experts = configs.get("experts", {})
    
    if not experts:
        return "No experts configured. Add them to config/experts.yaml"
    
    lines = ["## Available Experts\n"]
    for name, config in experts.items():
        desc = config.get("description", "No description")
        triggers = config.get("triggers", [])
        lines.append(f"### {name}")
        lines.append(f"Description: {desc}")
        if triggers:
            lines.append(f"Triggers: {', '.join(triggers)}")
        lines.append("")
    
    return "\n".join(lines)


@mcp.tool()
async def list_debiasing_techniques() -> str:
    """List available debiasing techniques.
    
    Returns:
        List of techniques with descriptions
    """
    from analyzers import get_debiasing_techniques, TECHNIQUE_NAMES_EN
    
    techniques = get_debiasing_techniques()
    
    descriptions = {
        "premortem": "Imagine the decision failed catastrophically - what went wrong?",
        "counterargs": "Generate the strongest arguments against this position",
        "uncertainty": "Identify areas of uncertainty and confidence levels",
        "assumptions": "Surface hidden assumptions that might be wrong",
        "reference_class": "Compare to similar historical cases for base rates",
        "change_mind": "What evidence would change your mind about this?"
    }
    
    lines = ["## Available Debiasing Techniques\n"]
    for tech in techniques:
        name = TECHNIQUE_NAMES_EN.get(tech, tech)
        desc = descriptions.get(tech, "No description")
        lines.append(f"- **{name}** (`{tech}`): {desc}")
    
    return "\n".join(lines)


# ============================================================================
# RESOURCES
# ============================================================================

@mcp.resource("config://providers")
async def get_providers_config() -> str:
    """Get current providers configuration."""
    from providers import load_configs
    configs = load_configs()
    return json.dumps(configs.get("providers", {}), indent=2)


@mcp.resource("config://user_model")
async def get_user_model() -> str:
    """Get current user model configuration."""
    from providers import load_configs
    configs = load_configs()
    return json.dumps(configs.get("user_model", {}), indent=2)


@mcp.resource("config://experts")
async def get_experts_config() -> str:
    """Get current experts configuration."""
    from providers import load_configs
    configs = load_configs()
    return json.dumps(configs.get("experts", {}), indent=2)


# ============================================================================
# PROMPTS
# ============================================================================

@mcp.prompt()
async def code_review_prompt(
    language: str = "python",
    focus: str = "security"
) -> str:
    """Generate a code review prompt for the council.
    
    Args:
        language: Programming language
        focus: Review focus area
    """
    return f"""Please review the following {language} code with a focus on {focus}.

Use the council to get multiple perspectives, then apply devil's advocate analysis.

Steps:
1. Use council_query to get initial review from multiple models
2. Use devils_advocate to find potential issues
3. Use run_debiasing with 'counterargs' and 'assumptions' techniques
4. Synthesize findings into actionable recommendations

Paste the code you want reviewed:"""


@mcp.prompt()
async def decision_analysis_prompt() -> str:
    """Generate a decision analysis prompt."""
    return """I'll help you analyze a decision using the Cognitive Stack.

Steps:
1. Use council_query to get multiple perspectives on the decision
2. Apply debiasing with 'premortem', 'counterargs', and 'assumptions'
3. Review variance analysis to see where models agree/disagree
4. Synthesize into a recommendation

Describe the decision you're considering:"""


@mcp.prompt()
async def code_generation_prompt(
    language: str = "python",
    task: str = ""
) -> str:
    """Generate a code generation prompt with quality checks.
    
    Args:
        language: Target programming language
        task: Description of what to build
    """
    return f"""I'll help you generate {language} code with quality assurance.

Task: {task if task else '[Describe what you want to build]'}

Steps:
1. Use council_query with 'architect' expert to design the solution
2. Generate the code
3. Use devils_advocate to review for issues
4. Use sonar_scan to check code quality
5. Use iterate_until_clean if issues are found

Let's start with the design phase."""


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run the MCP server."""
    import sys
    
    # Add current directory to path for imports
    sys.path.insert(0, str(Path(__file__).parent))
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Run server
    mcp.run()


if __name__ == "__main__":
    main()
