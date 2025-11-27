"""
Analyzers for variance detection and debiasing.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from providers import BaseProvider, Response

__all__ = [
    "VarianceReport",
    "DebiasingResult", 
    "analyze_variance",
    "run_debiasing",
    "format_debiasing_results",
    "DEBIASING_PROMPTS",
]

logger = logging.getLogger(__name__)


@dataclass
class VarianceReport:
    """Report on agreement/disagreement between models."""
    responses: list[Response]
    agreement_summary: str
    disagreement_points: list[str]
    confidence_signals: list[str]
    
    def format(self) -> str:
        """Format report as markdown."""
        lines = ["## Analiza Wariancji", ""]
        
        lines.append("### Zgoda")
        lines.append(self.agreement_summary or "_Brak danych_")
        lines.append("")
        
        if self.disagreement_points:
            lines.append("### Punkty Rozbieżności")
            for point in self.disagreement_points:
                lines.append(f"- {point}")
            lines.append("")
        
        if self.confidence_signals:
            lines.append("### Sygnały do Uwagi")
            for signal in self.confidence_signals:
                lines.append(f"⚠️ {signal}")
        
        return "\n".join(lines)


VARIANCE_ANALYSIS_PROMPT = """You are analyzing responses from multiple AI models to the same question.
Your task is to identify:
1. Where do the models AGREE? (These are more likely to be reliable)
2. Where do they DISAGREE? (These need human judgment)
3. What confidence signals should the user pay attention to?

Respond in this exact JSON format:
{
  "agreement_summary": "Brief summary of where models agree",
  "disagreement_points": ["Point 1", "Point 2"],
  "confidence_signals": ["Signal 1", "Signal 2"]
}

Be concise. Focus on actionable differences."""


def _parse_json_from_text(text: str) -> dict:
    """Extract and parse JSON from text, handling markdown code blocks."""
    content = text.strip()
    
    # Remove markdown code blocks if present
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(lines)
    
    # Find JSON object
    start = content.find("{")
    end = content.rfind("}") + 1
    
    if start >= 0 and end > start:
        return json.loads(content[start:end])
    
    raise ValueError("No valid JSON found in response")


async def analyze_variance(
    responses: list[Response],
    analyzer: BaseProvider
) -> VarianceReport:
    """Analyze variance between multiple model responses."""
    from providers import Response  # Import here to avoid circular import
    
    if not responses:
        return VarianceReport(
            responses=[],
            agreement_summary="Brak odpowiedzi do analizy.",
            disagreement_points=[],
            confidence_signals=[]
        )
    
    # Build context for analysis
    context_parts = ["Here are the responses from different models:\n"]
    for resp in responses:
        if resp.ok:
            context_parts.append(f"### {resp.provider} ({resp.model}):\n{resp.content}\n")
    
    context = "\n".join(context_parts)
    messages = [{"role": "user", "content": context}]
    
    result = await analyzer.complete(messages, system=VARIANCE_ANALYSIS_PROMPT)
    
    # Parse JSON response with fallback
    if result.ok and result.content:
        try:
            data = _parse_json_from_text(result.content)
        except ValueError as e:
            logger.warning(f"Failed to parse variance analysis JSON: {e}")
            data = {
                "agreement_summary": "Nie udało się przeanalizować automatycznie. Przejrzyj odpowiedzi ręcznie.",
                "disagreement_points": [],
                "confidence_signals": ["Analiza automatyczna nie powiodła się"]
            }
    else:
        data = {
            "agreement_summary": f"Analiza nie powiodła się: {result.error or 'Unknown error'}",
            "disagreement_points": [],
            "confidence_signals": ["Błąd podczas analizy wariancji"]
        }
    
    return VarianceReport(
        responses=responses,
        agreement_summary=data.get("agreement_summary", ""),
        disagreement_points=data.get("disagreement_points", []),
        confidence_signals=data.get("confidence_signals", [])
    )


# Debiasing prompts - templates for different analytical perspectives
DEBIASING_PROMPTS: dict[str, str] = {
    "premortem": """Przeprowadź pre-mortem tej decyzji/planu.
Załóżmy, że minął rok i ta decyzja okazała się KATASTROFĄ.
Opisz 5 najbardziej prawdopodobnych powodów, dlaczego to się nie udało.
Bądź konkretny i realistyczny.""",

    "counterargs": """Podaj 3 najsilniejsze kontrargumenty przeciwko powyższej rekomendacji.
Przedstaw je tak, jakby bronił ich ktoś inteligentny i kompetentny, 
kto naprawdę nie zgadza się z tą konkluzją.
Nie osłabiaj kontrargumentów - przedstaw je w najsilniejszej formie.""",

    "uncertainty": """Dla każdego kluczowego twierdzenia w powyższej odpowiedzi:
1. Oceń poziom pewności (0-100%)
2. Wskaż, co mogłoby zmienić tę ocenę
3. Zaznacz które elementy to fakty, a które opinie/spekulacje

Format: [TWIERDZENIE] → [X%] | [co mogłoby zmienić]""",

    "assumptions": """Jakie ukryte założenia przyjmuje powyższa odpowiedź?
Wymień wszystkie założenia, które muszą być prawdziwe, żeby rekomendacja była trafna.
Dla każdego założenia oceń jak ryzykowne by było gdyby okazało się fałszywe.""",

    "reference_class": """Jaka jest klasa referencyjna dla tej sytuacji?
Tzn. jak zazwyczaj wyglądają podobne przypadki statystycznie?
Czy ta sytuacja jest naprawdę wyjątkowa, czy to typowy przypadek?
Jakie są base rates dla sukcesu/porażki w podobnych sytuacjach?""",

    "change_mind": """Co musiałoby się stać lub jakie informacje musiałbyś otrzymać,
żeby ZMIENIĆ tę rekomendację na przeciwną?
Bądź konkretny - jakie dane, wydarzenia lub argumenty 
przekonałyby Cię do przeciwnej konkluzji?"""
}

TECHNIQUE_DISPLAY_NAMES: dict[str, str] = {
    "premortem": "🔮 Pre-mortem",
    "counterargs": "⚔️ Kontrargumenty", 
    "uncertainty": "📊 Niepewność",
    "assumptions": "🧱 Założenia",
    "reference_class": "📈 Klasa Referencyjna",
    "change_mind": "🔄 Co Zmieniłoby Zdanie"
}


@dataclass 
class DebiasingResult:
    """Result of a single debiasing technique."""
    technique: str
    analysis: str
    error: str | None = None
    
    @property
    def ok(self) -> bool:
        return self.error is None


async def _run_single_debiasing(
    technique: str,
    original_response: str,
    provider: BaseProvider,
    user_context: str = ""
) -> DebiasingResult:
    """Run a single debiasing technique."""
    prompt = DEBIASING_PROMPTS.get(technique)
    if not prompt:
        return DebiasingResult(
            technique=technique,
            analysis="",
            error=f"Unknown technique: {technique}"
        )
    
    context_parts = []
    if user_context:
        context_parts.append(f"Kontekst użytkownika: {user_context}")
    context_parts.append(f"Oryginalna odpowiedź:\n\n{original_response}")
    context_parts.append("---")
    context_parts.append(prompt)
    
    context = "\n\n".join(context_parts)
    messages = [{"role": "user", "content": context}]
    
    response = await provider.complete(messages)
    
    if response.ok:
        return DebiasingResult(technique=technique, analysis=response.content)
    else:
        return DebiasingResult(
            technique=technique,
            analysis="",
            error=response.error
        )


async def run_debiasing(
    original_response: str,
    techniques: list[str],
    provider: BaseProvider,
    user_context: str = "",
    parallel: bool = True
) -> list[DebiasingResult]:
    """
    Run debiasing techniques on a response.
    
    Args:
        original_response: The response to analyze
        techniques: List of technique names to run
        provider: LLM provider to use for analysis
        user_context: Additional context about the user
        parallel: If True, run techniques in parallel (faster but more API calls at once)
    
    Returns:
        List of DebiasingResult objects
    """
    valid_techniques = [t for t in techniques if t in DEBIASING_PROMPTS]
    
    if not valid_techniques:
        logger.warning(f"No valid debiasing techniques in: {techniques}")
        return []
    
    if parallel:
        # Run all techniques in parallel
        tasks = [
            _run_single_debiasing(t, original_response, provider, user_context)
            for t in valid_techniques
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(DebiasingResult(
                    technique=valid_techniques[i],
                    analysis="",
                    error=str(result)
                ))
            else:
                final_results.append(result)
        return final_results
    else:
        # Run sequentially
        results = []
        for technique in valid_techniques:
            result = await _run_single_debiasing(
                technique, original_response, provider, user_context
            )
            results.append(result)
        return results


def format_debiasing_results(results: list[DebiasingResult]) -> str:
    """Format debiasing results for display as markdown."""
    if not results:
        return "## Debiasing\n\n_Brak wyników debiasingu._"
    
    lines = ["## Debiasing", ""]
    
    for result in results:
        name = TECHNIQUE_DISPLAY_NAMES.get(result.technique, result.technique)
        lines.append(f"### {name}")
        
        if result.ok:
            lines.append(result.analysis)
        else:
            lines.append(f"_Błąd: {result.error}_")
        
        lines.append("")
    
    return "\n".join(lines)


def list_available_techniques() -> list[str]:
    """Return list of available debiasing techniques."""
    return list(DEBIASING_PROMPTS.keys())
