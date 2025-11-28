#!/usr/bin/env python3
"""
Cognitive Stack CLI - Multi-model council with debiasing.

Usage:
    ./council.py "Your question here"
    ./council.py "Question" --expert cost_cutter
    ./council.py "Question" --debias premortem,counterargs
    ./council.py --interactive
"""
from __future__ import annotations

import asyncio
import logging
import sys
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from dotenv import load_dotenv

# Load .env before other imports that might need env vars
load_dotenv()

import click
import yaml
from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from providers import (
    create_provider, 
    query_council, 
    close_all_providers,
    BaseProvider, 
    Response
)
from analyzers import (
    analyze_variance, 
    run_debiasing, 
    format_debiasing_results,
    list_available_techniques
)

__version__ = "1.4.0"

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)]
)
logger = logging.getLogger(__name__)

console = Console()
CONFIG_DIR = Path(__file__).parent / "config"

# Maximum query length to prevent abuse
MAX_QUERY_LENGTH = 32000


class ConfigError(Exception):
    """Configuration related errors."""
    pass


def load_yaml(path: Path) -> dict:
    """
    Load and validate YAML config file.
    
    Args:
        path: Path to YAML file
        
    Returns:
        Parsed YAML as dict
        
    Raises:
        ConfigError: If file doesn't exist or is invalid
    """
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if data is None:
                return {}
            if not isinstance(data, dict):
                raise ConfigError(f"Config must be a YAML mapping: {path}")
            return data
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {path}: {e}")


def load_configs() -> dict[str, dict]:
    """Load all configuration files."""
    return {
        "user_model": load_yaml(CONFIG_DIR / "user_model.yaml"),
        "experts": load_yaml(CONFIG_DIR / "experts.yaml"),
        "providers": load_yaml(CONFIG_DIR / "providers.yaml")
    }


def build_system_prompt(user_model: dict, expert: Optional[dict] = None) -> str:
    """Build system prompt from user model and optional expert persona."""
    parts = []
    
    # User context
    identity = user_model.get("identity", {})
    parts.append("## User Context")
    parts.append(f"Name: {identity.get('name', 'Unknown')}")
    parts.append(f"Role: {identity.get('role', 'Unknown')}")
    
    if goals := user_model.get("goals"):
        if isinstance(goals, list):
            parts.append(f"Goals: {', '.join(str(g) for g in goals)}")
    
    if constraints := user_model.get("constraints"):
        if isinstance(constraints, list):
            parts.append(f"Constraints: {', '.join(str(c) for c in constraints)}")
    
    parts.append(f"Risk tolerance: {user_model.get('risk_tolerance', 'medium')}")
    
    if ethics := user_model.get("ethics"):
        if isinstance(ethics, list):
            parts.append(f"Ethics: {', '.join(str(e) for e in ethics)}")
    
    # Communication style
    style = user_model.get("communication_style", {})
    lang = style.get("preferred_language", "en")
    parts.append(f"\nRespond in: {'Polish' if lang == 'pl' else 'English'}")
    parts.append(f"Verbosity: {style.get('verbosity', 'normal')}")
    parts.append(f"Technical depth: {style.get('technical_depth', 'intermediate')}")
    
    # Expert persona
    if expert:
        parts.append(f"\n## Your Role: {expert.get('name', 'Advisor')}")
        if system_prompt := expert.get("system_prompt"):
            parts.append(str(system_prompt))
    
    return "\n".join(parts)


def create_providers_from_config(config: dict) -> list[BaseProvider]:
    """Create provider instances from config."""
    providers_config = config.get("providers", {})
    default_council = providers_config.get("default_council", ["openai", "anthropic"])
    timeout = providers_config.get("timeout", 60)
    max_retries = providers_config.get("max_retries", 2)
    
    providers = []
    errors = []
    
    for name in default_council:
        # Use deepcopy to avoid mutating original config
        provider_conf = deepcopy(providers_config.get("providers", {}).get(name, {}))
        
        if not provider_conf:
            errors.append(f"{name}: not configured")
            continue
            
        if not provider_conf.get("enabled", True):
            continue
        
        # Add global settings
        provider_conf["timeout"] = timeout
        provider_conf["max_retries"] = max_retries
        
        try:
            providers.append(create_provider(name, provider_conf))
        except Exception as e:
            errors.append(f"{name}: {e}")
    
    for error in errors:
        console.print(f"[yellow]Warning: {error}[/yellow]")
    
    return providers


def display_response(resp: Response) -> None:
    """Display a single model response in a panel."""
    if resp.error:
        console.print(Panel(
            f"[red]Error: {resp.error}[/red]",
            title=f"❌ {resp.provider}",
            border_style="red"
        ))
    else:
        console.print(Panel(
            Markdown(resp.content),
            title=f"🤖 {resp.provider} ({resp.model})",
            border_style="blue"
        ))


async def run_council(
    query: str,
    configs: dict,
    expert_name: Optional[str] = None,
    debias_techniques: Optional[list[str]] = None,
    show_variance: bool = True
) -> None:
    """Run the full council pipeline."""
    # Validate query length
    if len(query) > MAX_QUERY_LENGTH:
        console.print(f"[red]Query too long. Maximum {MAX_QUERY_LENGTH} characters.[/red]")
        return
    
    # Get user language preference
    user_model = configs.get("user_model", {})
    communication_style = user_model.get("communication_style", {})
    language = communication_style.get("preferred_language", "en")
    
    # Build system prompt
    expert = None
    if expert_name:
        experts_config = configs.get("experts", {}).get("experts", {})
        expert = experts_config.get(expert_name)
        if not expert:
            available = list(experts_config.keys())
            console.print(f"[yellow]Expert '{expert_name}' not found. Available: {available}[/yellow]")
    
    system_prompt = build_system_prompt(user_model, expert)
    
    # Create providers
    providers = create_providers_from_config(configs)
    if not providers:
        console.print("[red]No providers available. Check your API keys and config.[/red]")
        return
    
    try:
        console.print(f"\n[dim]Querying {len(providers)} models...[/dim]\n")
        
        # Query council
        messages = [{"role": "user", "content": query}]
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task("Waiting for responses...", total=None)
            responses = await query_council(providers, messages, system_prompt)
            progress.remove_task(task)
        
        # Display individual responses
        for resp in responses:
            display_response(resp)
            console.print()
        
        # Variance analysis
        successful_responses = [r for r in responses if r.ok]
        
        if show_variance and len(successful_responses) > 1:
            console.print("[dim]Analyzing variance...[/dim]\n")
            variance_report = await analyze_variance(successful_responses, providers[0], language)
            console.print(Panel(
                Markdown(variance_report.format()),
                title="📊 Variance Analysis",
                border_style="green"
            ))
            console.print()
        
        # Debiasing
        if debias_techniques and successful_responses:
            console.print("[dim]Running debiasing protocols...[/dim]\n")
            combined = "\n\n---\n\n".join([
                f"**{r.provider}**: {r.content}" for r in successful_responses
            ])
            user_goals = user_model.get("goals", [])
            user_context = f"Goals: {user_goals}" if user_goals else ""
            
            debias_results = await run_debiasing(
                combined, debias_techniques, providers[0], user_context, parallel=True, language=language
            )
            console.print(Panel(
                Markdown(format_debiasing_results(debias_results, language)),
                title="🎯 Debiasing Results",
                border_style="yellow"
            ))
    
    finally:
        await close_all_providers(providers)


# ============================================================================
# Interactive Mode - Refactored with command handlers
# ============================================================================

@dataclass
class InteractiveState:
    """State for interactive session."""
    configs: dict
    current_expert: Optional[str] = None
    current_debias: list[str] = field(default_factory=list)
    running: bool = True


def _cmd_quit(state: InteractiveState, arg: str) -> None:
    """Handle /quit and /exit commands."""
    console.print("[dim]Goodbye![/dim]")
    state.running = False


def _cmd_expert(state: InteractiveState, arg: str) -> None:
    """Handle /expert command."""
    experts = state.configs.get("experts", {}).get("experts", {})
    
    if not arg:
        state.current_expert = None
        console.print("[dim]Expert reset to default[/dim]")
        return
    
    if arg in experts:
        state.current_expert = arg
        console.print(f"[green]Expert set to: {arg}[/green]")
    else:
        console.print(f"[yellow]Unknown expert: {arg}. Use /list-experts[/yellow]")


def _cmd_debias(state: InteractiveState, arg: str) -> None:
    """Handle /debias command."""
    if not arg:
        console.print(f"[dim]Current debiasing: {state.current_debias or 'none'}[/dim]")
        return
    
    techniques = [t.strip() for t in arg.split(",")]
    available = set(list_available_techniques())
    valid = [t for t in techniques if t in available]
    invalid = [t for t in techniques if t not in available]
    
    if invalid:
        console.print(f"[yellow]Unknown techniques: {invalid}[/yellow]")
    
    state.current_debias = valid
    console.print(f"[green]Debiasing: {state.current_debias or 'none'}[/green]")


def _cmd_clear(state: InteractiveState, arg: str) -> None:
    """Handle /clear command."""
    state.current_debias = []
    console.print("[dim]Debiasing cleared[/dim]")


def _cmd_list_experts(state: InteractiveState, arg: str) -> None:
    """Handle /list-experts command."""
    experts = state.configs.get("experts", {}).get("experts", {})
    console.print("\n[bold]Available Experts:[/bold]")
    for name, exp in experts.items():
        desc = exp.get("description", "")
        marker = "→" if name == state.current_expert else " "
        console.print(f"  {marker} [cyan]{name}[/cyan]: {desc}")


def _cmd_list_debias(state: InteractiveState, arg: str) -> None:
    """Handle /list-debias command."""
    available = list_available_techniques()
    current_set = set(state.current_debias)
    console.print("\n[bold]Available Debiasing Techniques:[/bold]")
    for t in available:
        marker = "✓" if t in current_set else " "
        console.print(f"  {marker} [cyan]{t}[/cyan]")


def _cmd_help(state: InteractiveState, arg: str) -> None:
    """Handle /help command."""
    console.print("Commands: /expert, /debias, /clear, /list-experts, /list-debias, /quit")


# Command handler registry
INTERACTIVE_COMMANDS: dict[str, Callable[[InteractiveState, str], None]] = {
    "/quit": _cmd_quit,
    "/exit": _cmd_quit,
    "/expert": _cmd_expert,
    "/debias": _cmd_debias,
    "/clear": _cmd_clear,
    "/list-experts": _cmd_list_experts,
    "/list-debias": _cmd_list_debias,
    "/help": _cmd_help,
}


def _show_interactive_help() -> None:
    """Display interactive mode welcome message."""
    console.print(Panel(
        "[bold]Cognitive Stack - Interactive Mode[/bold]\n\n"
        "Commands:\n"
        "  /expert <name>     - Switch expert persona\n"
        "  /debias <t1,t2>    - Set debiasing techniques\n"
        "  /clear             - Clear debiasing\n"
        "  /list-experts      - Show available experts\n"
        "  /list-debias       - Show available debiasing techniques\n"
        "  /help              - Show this help\n"
        "  /quit              - Exit\n",
        border_style="cyan"
    ))


def _handle_command(state: InteractiveState, query: str) -> None:
    """Handle a slash command."""
    parts = query.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    
    handler = INTERACTIVE_COMMANDS.get(cmd)
    if handler:
        handler(state, arg)
    else:
        console.print(f"[yellow]Unknown command: {cmd}. Try /help[/yellow]")


async def interactive_mode(configs: dict) -> None:
    """Interactive session mode with persistent state."""
    _show_interactive_help()
    
    state = InteractiveState(configs=configs)
    
    while state.running:
        try:
            query = console.input("\n[bold cyan]You:[/bold cyan] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break
        
        if not query:
            continue
        
        if query.startswith("/"):
            _handle_command(state, query)
            continue
        
        await run_council(
            query,
            configs,
            expert_name=state.current_expert,
            debias_techniques=state.current_debias if state.current_debias else None
        )


# ============================================================================
# CLI Entry Point
# ============================================================================

@click.command()
@click.argument("query", required=False)
@click.option("--expert", "-e", help="Expert persona to use")
@click.option("--debias", "-d", help="Debiasing techniques (comma-separated)")
@click.option("--interactive", "-i", is_flag=True, help="Interactive session mode")
@click.option("--no-variance", is_flag=True, help="Skip variance analysis")
@click.option("--list-experts", is_flag=True, help="List available experts")
@click.option("--list-debias", is_flag=True, help="List available debiasing techniques")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.version_option(version=__version__)
def main(
    query: Optional[str],
    expert: Optional[str],
    debias: Optional[str],
    interactive: bool,
    no_variance: bool,
    list_experts: bool,
    list_debias: bool,
    verbose: bool
) -> None:
    """Query multiple LLMs with cognitive stack enhancements."""
    
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        configs = load_configs()
    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        sys.exit(1)
    
    if list_experts:
        console.print("\n[bold]Available Experts:[/bold]\n")
        for name, exp in configs.get("experts", {}).get("experts", {}).items():
            console.print(f"  [cyan]{name}[/cyan]: {exp.get('description', '')}")
        return
    
    if list_debias:
        console.print("\n[bold]Available Debiasing Techniques:[/bold]\n")
        for technique in list_available_techniques():
            console.print(f"  [cyan]{technique}[/cyan]")
        return
    
    if interactive:
        asyncio.run(interactive_mode(configs))
        return
    
    if not query:
        console.print("[red]Please provide a query or use --interactive mode.[/red]")
        console.print("Usage: ./council.py 'Your question here'")
        console.print("       ./council.py --interactive")
        sys.exit(1)
    
    debias_techniques = None
    if debias:
        debias_techniques = [t.strip() for t in debias.split(",")]
    
    asyncio.run(run_council(
        query,
        configs,
        expert_name=expert,
        debias_techniques=debias_techniques,
        show_variance=not no_variance
    ))


if __name__ == "__main__":
    main()
