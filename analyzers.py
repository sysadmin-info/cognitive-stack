"""
Analyzers for variance detection and debiasing.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from providers import BaseProvider, Response

__all__ = [
    "VarianceReport",
    "DebiasingResult", 
    "analyze_variance",
    "run_debiasing",
    "format_debiasing_results",
    "get_debiasing_techniques",
    "get_prompts_for_language",
    "get_technique_names_for_language",
    "get_labels_for_language",
    "DEBIASING_PROMPTS",
    "DEBIASING_PROMPTS_EN",
    "DEBIASING_PROMPTS_PL",
]

logger = logging.getLogger(__name__)

# =============================================================================
# Bilingual Labels and Prompts
# =============================================================================

LABELS = {
    "pl": {
        "variance_title": "## Analiza Wariancji",
        "agreement": "### Zgoda",
        "disagreement": "### Punkty Rozbieżności",
        "signals": "### Sygnały do Uwagi",
        "no_data": "_Brak danych_",
        "debiasing_title": "## Debiasing",
    },
    "en": {
        "variance_title": "## Variance Analysis",
        "agreement": "### Agreement",
        "disagreement": "### Disagreement Points",
        "signals": "### Signals to Watch",
        "no_data": "_No data_",
        "debiasing_title": "## Debiasing",
    }
}

DEBIASING_PROMPTS_PL: dict[str, str] = {
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

DEBIASING_PROMPTS_EN: dict[str, str] = {
    "premortem": """Conduct a pre-mortem analysis of this decision/plan.
Assume one year has passed and this decision turned out to be a DISASTER.
Describe the 5 most likely reasons why it failed.
Be specific and realistic.""",

    "counterargs": """Provide 3 strongest counterarguments against the recommendation above.
Present them as if defended by someone intelligent and competent,
who genuinely disagrees with this conclusion.
Don't weaken the counterarguments - present them in their strongest form.""",

    "uncertainty": """For each key claim in the response above:
1. Assess confidence level (0-100%)
2. Indicate what could change this assessment
3. Mark which elements are facts vs opinions/speculation

Format: [CLAIM] → [X%] | [what could change it]""",

    "assumptions": """What hidden assumptions does the response above make?
List all assumptions that must be true for the recommendation to be valid.
For each assumption, assess how risky it would be if it turned out to be false.""",

    "reference_class": """What is the reference class for this situation?
I.e., how do similar cases typically look statistically?
Is this situation truly exceptional, or is it a typical case?
What are the base rates for success/failure in similar situations?""",

    "change_mind": """What would need to happen or what information would you need to receive
to CHANGE this recommendation to the opposite?
Be specific - what data, events, or arguments 
would convince you of the opposite conclusion?"""
}

TECHNIQUE_NAMES_PL: dict[str, str] = {
    "premortem": "🔮 Pre-mortem",
    "counterargs": "⚔️ Kontrargumenty", 
    "uncertainty": "📊 Niepewność",
    "assumptions": "🧱 Założenia",
    "reference_class": "📈 Klasa Referencyjna",
    "change_mind": "🔄 Co Zmieniłoby Zdanie"
}

TECHNIQUE_NAMES_EN: dict[str, str] = {
    "premortem": "🔮 Pre-mortem",
    "counterargs": "⚔️ Counterarguments", 
    "uncertainty": "📊 Uncertainty",
    "assumptions": "🧱 Assumptions",
    "reference_class": "📈 Reference Class",
    "change_mind": "🔄 What Would Change Your Mind"
}

# Default (for backwards compatibility)
DEBIASING_PROMPTS = DEBIASING_PROMPTS_EN
TECHNIQUE_DISPLAY_NAMES = TECHNIQUE_NAMES_EN


def get_prompts_for_language(lang: str = "en") -> dict[str, str]:
    """Get debiasing prompts for specified language."""
    if lang.lower().startswith("pl"):
        return DEBIASING_PROMPTS_PL
    return DEBIASING_PROMPTS_EN


def get_technique_names_for_language(lang: str = "en") -> dict[str, str]:
    """Get technique display names for specified language."""
    if lang.lower().startswith("pl"):
        return TECHNIQUE_NAMES_PL
    return TECHNIQUE_NAMES_EN


def get_labels_for_language(lang: str = "en") -> dict[str, str]:
    """Get UI labels for specified language."""
    if lang.lower().startswith("pl"):
        return LABELS["pl"]
    return LABELS["en"]


@dataclass
class VarianceReport:
    """Report on agreement/disagreement between models."""
    responses: list[Response]
    agreement_summary: str
    disagreement_points: list[str]
    confidence_signals: list[str]
    language: str = "en"
    
    def format(self) -> str:
        """Format report as markdown."""
        labels = get_labels_for_language(self.language)
        
        lines = [labels["variance_title"], ""]
        
        lines.append(labels["agreement"])
        lines.append(self.agreement_summary or labels["no_data"])
        lines.append("")
        
        if self.disagreement_points:
            lines.append(labels["disagreement"])
            for point in self.disagreement_points:
                lines.append(f"- {point}")
            lines.append("")
        
        if self.confidence_signals:
            lines.append(labels["signals"])
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
    analyzer: BaseProvider,
    language: str = "en"
) -> VarianceReport:
    """Analyze variance between multiple model responses."""
    from providers import Response  # Import here to avoid circular import
    
    labels = get_labels_for_language(language)
    
    if not responses:
        no_responses_msg = "No responses to analyze." if language == "en" else "Brak odpowiedzi do analizy."
        return VarianceReport(
            responses=[],
            agreement_summary=no_responses_msg,
            disagreement_points=[],
            confidence_signals=[],
            language=language
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
            fallback_msg = (
                "Could not analyze automatically. Please review responses manually."
                if language == "en" else 
                "Nie udało się przeanalizować automatycznie. Przejrzyj odpowiedzi ręcznie."
            )
            fallback_signal = (
                "Automatic analysis failed"
                if language == "en" else
                "Analiza automatyczna nie powiodła się"
            )
            data = {
                "agreement_summary": fallback_msg,
                "disagreement_points": [],
                "confidence_signals": [fallback_signal]
            }
    else:
        error_msg = (
            f"Analysis failed: {result.error or 'Unknown error'}"
            if language == "en" else
            f"Analiza nie powiodła się: {result.error or 'Unknown error'}"
        )
        error_signal = (
            "Error during variance analysis"
            if language == "en" else
            "Błąd podczas analizy wariancji"
        )
        data = {
            "agreement_summary": error_msg,
            "disagreement_points": [],
            "confidence_signals": [error_signal]
        }
    
    return VarianceReport(
        responses=responses,
        agreement_summary=data.get("agreement_summary", ""),
        disagreement_points=data.get("disagreement_points", []),
        confidence_signals=data.get("confidence_signals", []),
        language=language
    )




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
    user_context: str = "",
    language: str = "en"
) -> DebiasingResult:
    """Run a single debiasing technique."""
    prompts = get_prompts_for_language(language)
    prompt = prompts.get(technique)
    if not prompt:
        return DebiasingResult(
            technique=technique,
            analysis="",
            error=f"Unknown technique: {technique}"
        )
    
    context_label = "User context:" if language == "en" else "Kontekst użytkownika:"
    response_label = "Original response:" if language == "en" else "Oryginalna odpowiedź:"
    
    context_parts = []
    if user_context:
        context_parts.append(f"{context_label} {user_context}")
    context_parts.append(f"{response_label}\n\n{original_response}")
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
    parallel: bool = True,
    language: str = "en"
) -> list[DebiasingResult]:
    """
    Run debiasing techniques on a response.
    
    Args:
        original_response: The response to analyze
        techniques: List of technique names to run
        provider: LLM provider to use for analysis
        user_context: Additional context about the user
        parallel: If True, run techniques in parallel (faster but more API calls at once)
        language: Language for prompts ("en" or "pl")
    
    Returns:
        List of DebiasingResult objects
    """
    prompts = get_prompts_for_language(language)
    valid_techniques = [t for t in techniques if t in prompts]
    
    if not valid_techniques:
        logger.warning(f"No valid debiasing techniques in: {techniques}")
        return []
    
    if parallel:
        # Run all techniques in parallel
        tasks = [
            _run_single_debiasing(t, original_response, provider, user_context, language)
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
                technique, original_response, provider, user_context, language
            )
            results.append(result)
        return results


def format_debiasing_results(results: list[DebiasingResult], language: str = "en") -> str:
    """Format debiasing results for display as markdown."""
    labels = get_labels_for_language(language)
    technique_names = get_technique_names_for_language(language)
    
    no_results_msg = "_No debiasing results._" if language == "en" else "_Brak wyników debiasingu._"
    
    if not results:
        return f"{labels['debiasing_title']}\n\n{no_results_msg}"
    
    lines = [labels["debiasing_title"], ""]
    
    for result in results:
        name = technique_names.get(result.technique, result.technique)
        lines.append(f"### {name}")
        
        if result.ok:
            lines.append(result.analysis)
        else:
            error_prefix = "Error:" if language == "en" else "Błąd:"
            lines.append(f"_{error_prefix} {result.error}_")
        
        lines.append("")
    
    return "\n".join(lines)


def get_debiasing_techniques() -> list[str]:
    """Return list of available debiasing techniques."""
    return list(DEBIASING_PROMPTS_EN.keys())


def list_available_techniques() -> list[str]:
    """Return list of available debiasing techniques (alias for backwards compatibility)."""
    return get_debiasing_techniques()
