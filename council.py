#!/usr/bin/env python3
"""
Cognitive Stack CLI - Multi-model council with debiasing.

Usage:
    ./council.py "Your question here"
    ./council.py "Question" --expert cost_cutter
    ./council.py "Question" --debias premortem,counterargs
    ./council.py --interactive
"""
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env before anything else
load_dotenv()

import click
import yaml
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from providers import create_provider, query_council, BaseProvider, Response
from analyzers import analyze_variance, run_debiasing, format_debiasing_results


console = Console()
CONFIG_DIR = Path(__file__).parent / "config"


def load_yaml(path: Path) -> dict:
    """Load YAML config file."""
    if not path.exists():
        console.print(f"[red]Config not found: {path}[/red]")
        sys.exit(1)
    with open(path) as f:
        return yaml.safe_load(f)


def load_configs():
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
    um = user_model
    parts.append("## User Context")
    parts.append(f"Name: {um.get('identity', {}).get('name', 'Unknown')}")
    parts.append(f"Role: {um.get('identity', {}).get('role', 'Unknown')}")
    
    if goals := um.get("goals"):
        parts.append(f"Goals: {', '.join(goals)}")
    
    if constraints := um.get("constraints"):
        parts.append(f"Constraints: {', '.join(constraints)}")
    
    parts.append(f"Risk tolerance: {um.get('risk_tolerance', 'medium')}")
    
    if ethics := um.get("ethics"):
        parts.append(f"Ethics: {', '.join(ethics)}")
    
    # Communication style
    style = um.get("communication_style", {})
    lang = style.get("preferred_language", "en")
    parts.append(f"\nRespond in: {'Polish' if lang == 'pl' else 'English'}")
    parts.append(f"Verbosity: {style.get('verbosity', 'normal')}")
    parts.append(f"Technical depth: {style.get('technical_depth', 'intermediate')}")
    
    # Expert persona
    if expert:
        parts.append(f"\n## Your Role: {expert.get('name', 'Advisor')}")
        parts.append(expert.get("system_prompt", ""))
    
    return "\n".join(parts)


def create_providers_from_config(config: dict) -> list[BaseProvider]:
    """Create provider instances from config."""
    providers_config = config["providers"]
    default_council = providers_config.get("default_council", ["openai", "anthropic"])
    timeout = providers_config.get("timeout", 60)
    
    providers = []
    for name in default_council:
        provider_conf = providers_config.get("providers", {}).get(name, {})
        if not provider_conf.get("enabled", True):
            continue
        provider_conf["timeout"] = timeout
        try:
            providers.append(create_provider(name, provider_conf))
        except Exception as e:
            console.print(f"[yellow]Warning: Could not create {name}: {e}[/yellow]")
    
    return providers


def display_response(resp: Response):
    """Display a single model response."""
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
):
    """Run the full council pipeline."""
    
    # Build system prompt
    expert = None
    if expert_name:
        experts_config = configs["experts"].get("experts", {})
        expert = experts_config.get(expert_name)
        if not expert:
            console.print(f"[yellow]Expert '{expert_name}' not found. Using default.[/yellow]")
    
    system_prompt = build_system_prompt(configs["user_model"], expert)
    
    # Create providers
    providers = create_providers_from_config(configs)
    if not providers:
        console.print("[red]No providers available. Check your API keys.[/red]")
        return
    
    console.print(f"\n[dim]Querying {len(providers)} models...[/dim]\n")
    
    # Query council
    messages = [{"role": "user", "content": query}]
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
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
        
        # Use first available provider for analysis
        analyzer = providers[0]
        variance_report = await analyze_variance(successful_responses, analyzer)
        
        console.print(Panel(
            Markdown(variance_report.format()),
            title="📊 Variance Analysis",
            border_style="green"
        ))
        console.print()
    
    # Debiasing
    if debias_techniques and successful_responses:
        console.print("[dim]Running debiasing protocols...[/dim]\n")
        
        # Combine responses for debiasing
        combined = "\n\n---\n\n".join([
            f"**{r.provider}**: {r.content}" for r in successful_responses
        ])
        
        user_context = f"Goals: {configs['user_model'].get('goals', [])}"
        
        debias_results = await run_debiasing(
            combined,
            debias_techniques,
            providers[0],
            user_context
        )
        
        console.print(Panel(
            Markdown(format_debiasing_results(debias_results)),
            title="🎯 Debiasing Results",
            border_style="yellow"
        ))


async def interactive_mode(configs: dict):
    """Interactive session mode."""
    console.print(Panel(
        "[bold]Cognitive Stack - Interactive Mode[/bold]\n\n"
        "Commands:\n"
        "  /expert <name>  - Switch expert persona\n"
        "  /debias <t1,t2> - Set debiasing (premortem,counterargs,uncertainty,assumptions,reference_class,change_mind)\n"
        "  /clear          - Clear debiasing\n"
        "  /help           - Show this help\n"
        "  /quit           - Exit\n",
        border_style="cyan"
    ))
    
    current_expert = None
    current_debias = []
    
    while True:
        try:
            query = console.input("\n[bold cyan]You:[/bold cyan] ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        
        if not query:
            continue
        
        if query.startswith("/"):
            parts = query.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""
            
            if cmd == "/quit":
                break
            elif cmd == "/expert":
                current_expert = arg if arg else None
                console.print(f"[dim]Expert set to: {current_expert or 'default'}[/dim]")
            elif cmd == "/debias":
                current_debias = [t.strip() for t in arg.split(",")] if arg else []
                console.print(f"[dim]Debiasing: {current_debias or 'none'}[/dim]")
            elif cmd == "/clear":
                current_debias = []
                console.print("[dim]Debiasing cleared[/dim]")
            elif cmd == "/help":
                console.print("Commands: /expert, /debias, /clear, /quit")
            else:
                console.print(f"[yellow]Unknown command: {cmd}[/yellow]")
            continue
        
        await run_council(
            query,
            configs,
            expert_name=current_expert,
            debias_techniques=current_debias if current_debias else None
        )


@click.command()
@click.argument("query", required=False)
@click.option("--expert", "-e", help="Expert persona to use (strategist, cost_cutter, security_auditor, operator, devils_advocate, coach)")
@click.option("--debias", "-d", help="Debiasing techniques (comma-separated: premortem,counterargs,uncertainty,assumptions,reference_class,change_mind)")
@click.option("--interactive", "-i", is_flag=True, help="Interactive session mode")
@click.option("--no-variance", is_flag=True, help="Skip variance analysis")
@click.option("--list-experts", is_flag=True, help="List available experts")
def main(query, expert, debias, interactive, no_variance, list_experts):
    """Query multiple LLMs with cognitive stack enhancements."""
    
    configs = load_configs()
    
    if list_experts:
        console.print("\n[bold]Available Experts:[/bold]\n")
        for name, exp in configs["experts"].get("experts", {}).items():
            console.print(f"  [cyan]{name}[/cyan]: {exp.get('description', '')}")
        return
    
    if interactive:
        asyncio.run(interactive_mode(configs))
        return
    
    if not query:
        console.print("[red]Please provide a query or use --interactive mode.[/red]")
        console.print("Usage: ./council.py 'Your question here'")
        return
    
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
