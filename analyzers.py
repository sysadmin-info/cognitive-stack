"""
Analyzers for variance detection and debiasing.
"""
from dataclasses import dataclass
from providers import Response, BaseProvider


@dataclass
class VarianceReport:
    """Report on agreement/disagreement between models."""
    responses: list[Response]
    agreement_summary: str
    disagreement_points: list[str]
    confidence_signals: list[str]
    
    def format(self) -> str:
        lines = ["## Analiza Wariancji", ""]
        
        lines.append("### Zgoda")
        lines.append(self.agreement_summary)
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


async def analyze_variance(
    responses: list[Response],
    analyzer: BaseProvider
) -> VarianceReport:
    """Analyze variance between multiple model responses."""
    
    # Build context for analysis
    context = "Here are the responses from different models:\n\n"
    for resp in responses:
        if resp.ok:
            context += f"### {resp.provider} ({resp.model}):\n{resp.content}\n\n"
    
    messages = [{"role": "user", "content": context}]
    
    result = await analyzer.complete(messages, system=VARIANCE_ANALYSIS_PROMPT)
    
    # Parse JSON response (with fallback)
    import json
    try:
        # Find JSON in response
        content = result.content
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
        else:
            raise ValueError("No JSON found")
    except (json.JSONDecodeError, ValueError):
        # Fallback
        data = {
            "agreement_summary": "Nie udało się przeanalizować automatycznie. Przejrzyj odpowiedzi ręcznie.",
            "disagreement_points": [],
            "confidence_signals": ["Analiza automatyczna nie powiodła się"]
        }
    
    return VarianceReport(
        responses=responses,
        agreement_summary=data.get("agreement_summary", ""),
        disagreement_points=data.get("disagreement_points", []),
        confidence_signals=data.get("confidence_signals", [])
    )


# Debiasing prompts
DEBIASING_PROMPTS = {
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


@dataclass 
class DebiasingResult:
    technique: str
    analysis: str


async def run_debiasing(
    original_response: str,
    techniques: list[str],
    provider: BaseProvider,
    user_context: str = ""
) -> list[DebiasingResult]:
    """Run debiasing techniques on a response."""
    results = []
    
    for technique in techniques:
        if technique not in DEBIASING_PROMPTS:
            continue
        
        prompt = DEBIASING_PROMPTS[technique]
        context = f"Oryginalna odpowiedź:\n\n{original_response}\n\n---\n\n{prompt}"
        
        if user_context:
            context = f"Kontekst użytkownika: {user_context}\n\n{context}"
        
        messages = [{"role": "user", "content": context}]
        response = await provider.complete(messages)
        
        if response.ok:
            results.append(DebiasingResult(technique=technique, analysis=response.content))
    
    return results


def format_debiasing_results(results: list[DebiasingResult]) -> str:
    """Format debiasing results for display."""
    lines = ["## Debiasing", ""]
    
    technique_names = {
        "premortem": "🔮 Pre-mortem",
        "counterargs": "⚔️ Kontrargumenty", 
        "uncertainty": "📊 Niepewność",
        "assumptions": "🧱 Założenia",
        "reference_class": "📈 Klasa Referencyjna",
        "change_mind": "🔄 Co Zmieniłoby Zdanie"
    }
    
    for result in results:
        name = technique_names.get(result.technique, result.technique)
        lines.append(f"### {name}")
        lines.append(result.analysis)
        lines.append("")
    
    return "\n".join(lines)
