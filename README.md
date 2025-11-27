# Cognitive Stack

CLI do orkiestracji wielu modeli LLM z analizą wariancji i protokołami debiasingu.

Inspiracja: [Synthetic Cognitive Systems](https://www.linkedin.com/posts/pawelpszczesny_ask-three-models-llm-council-is-the-first-activity-7399323058169188352-EaBD?utm_source=social_share_send&utm_medium=android_app&rcm=ACoAACUmdFUByw_8om7AOfbbt_Y2whMI-6rmMmY&utm_campaign=share_via) - od "zapytaj 3 modele" do zaprojektowanej inteligencji.

## Instalacja

```bash
# Klonuj lub pobierz projekt
cd cognitive-stack

# Stwórz venv
python3 -m venv venv
source venv/bin/activate

# Zainstaluj zależności
pip install -r requirements.txt

# Skonfiguruj API keys
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="..."

# Opcjonalnie: dodaj do .bashrc/.zshrc
```

## Konfiguracja

### config/user_model.yaml

Twój profil - modele używają tego zamiast dawać generyczne rady:

```yaml
identity:
  name: "Adrian"
  role: "Security Engineer"

goals:
  - "Automatyzacja bez vendor lock-in"

constraints:
  - "Ograniczony budżet"
  - "Musi działać air-gapped"

risk_tolerance: "low-to-medium"
```

### config/experts.yaml

Różne "czapki" ekspertów, które możesz nakładać:

- `strategist` - myślenie długoterminowe
- `cost_cutter` - pragmatyczny, ROI
- `security_auditor` - paranoidny, threat modeling
- `operator` - SRE, day-2 operations
- `devils_advocate` - szuka dziur
- `coach` - czynnik ludzki

### config/providers.yaml

Konfiguracja API (modele, timeouty, klucze).

## Użycie

### Podstawowe zapytanie (rada 3 modeli)

```bash
./council.py "Czy powinienem wdrożyć Kubernetes w homelabie?"
```

### Z konkretnym ekspertem

```bash
./council.py "Czy wdrożyć K8s?" --expert cost_cutter
./council.py "Czy wdrożyć K8s?" --expert security_auditor
```

### Z debiasingiem

```bash
# Pre-mortem
./council.py "Plan migracji do clouda" --debias premortem

# Wiele technik
./council.py "Plan migracji" --debias premortem,counterargs,uncertainty
```

Dostępne techniki debiasingu:
- `premortem` - co poszło nie tak za rok?
- `counterargs` - najsilniejsze kontrargumenty
- `uncertainty` - poziomy pewności dla każdego twierdzenia
- `assumptions` - ukryte założenia
- `reference_class` - jak to wygląda statystycznie?
- `change_mind` - co zmieniłoby zdanie?

### Tryb interaktywny

```bash
./council.py --interactive
```

Komendy w trybie interaktywnym:
- `/expert cost_cutter` - zmień eksperta
- `/debias premortem,counterargs` - ustaw debiasing
- `/clear` - wyczyść debiasing
- `/quit` - wyjście

### Lista ekspertów

```bash
./council.py --list-experts
```

## Architektura

```
Query → [User Model] → [Expert Persona] → System Prompt
                                               ↓
                            ┌──────────────────┼──────────────────┐
                            ↓                  ↓                  ↓
                         OpenAI            Anthropic           Google
                            ↓                  ↓                  ↓
                            └──────────────────┼──────────────────┘
                                               ↓
                                    [Variance Analyzer]
                                               ↓
                                    [Debiasing Protocols]
                                               ↓
                                         Output
```

## Rozszerzenia

### Dodawanie nowych providerów

1. Dodaj klasę w `providers.py` dziedziczącą po `BaseProvider`
2. Zarejestruj w `PROVIDER_CLASSES`
3. Dodaj konfigurację w `config/providers.yaml`

### Dodawanie ekspertów

Edytuj `config/experts.yaml`:

```yaml
experts:
  my_expert:
    name: "My Expert"
    description: "What they do"
    system_prompt: |
      Your instructions here...
    triggers:
      - "keyword1"
      - "keyword2"
```

### Dodawanie technik debiasingu

Dodaj prompt w `analyzers.py` → `DEBIASING_PROMPTS`.

## Przyszłe rozszerzenia

- [ ] Ollama dla modeli lokalnych (config gotowy)
- [ ] Zapisywanie sesji do plików
- [ ] Integracja z notatkami głosowymi (intuicja jako dane)
- [ ] Auto-matching ekspertów na podstawie triggerów
- [ ] Pipeline w YAML (łańcuchy agentów)
