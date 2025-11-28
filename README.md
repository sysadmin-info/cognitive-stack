# Cognitive Stack

**CLI do orkiestracji wielu modeli LLM z analizą wariancji i protokołami debiasingu.**

---

## Spis treści / Table of Contents

- [Polski](#cognitive-stack---polska-wersja)
- [English](#cognitive-stack---english-version)

---

# Cognitive Stack - Polska wersja

## Geneza projektu

Projekt inspirowany koncepcją **"Synthetic Cognitive Systems"** - przejście od prostego "zapytaj 3 modele" do zaprojektowanego stosu kognitywnego.

**Kluczowa filozofia:** Przestać traktować AI jak chatbota, zacząć traktować jak zaprojektowany proces decyzyjny.

Więcej o koncepcji: [LinkedIn - Synthetic Cognitive Systems](https://www.linkedin.com/posts/pawelpszczesny_ask-three-models-llm-council-is-the-first-activity-7399323058169188352-EaBD?utm_source=social_share_send&utm_medium=android_app&rcm=ACoAACUmdFUByw_8om7AOfbbt_Y2whMI-6rmMmY&utm_campaign=share_via)

### Pięć poziomów stosu kognitywnego:

1. **LLM-Council** - wariancja jako sygnał (gdzie modele się zgadzają = większa pewność)
2. **User Model** - profil użytkownika (cele, ograniczenia, tolerancja ryzyka)
3. **Expert Matching** - dopasowanie persony eksperta do kontekstu pytania
4. **Debiasing Protocols** - wymuszanie krytycznego myślenia (pre-mortem, kontrargumenty)
5. **Intuition as Data** - protokoły dla przeczuć i nieoczywistych sygnałów

## Architektura

```
cognitive-stack/
├── council.py          # Główny CLI entry point
├── providers.py        # Klienty API (OpenAI, Anthropic, Google, Ollama, LM Studio)
├── analyzers.py        # Analiza wariancji + techniki debiasingu
├── config/
│   ├── providers.yaml  # Konfiguracja providerów API
│   ├── experts.yaml    # Definicje person ekspertów
│   └── user_model.yaml # Profil użytkownika
├── .env                # Klucze API (nie commitować!)
└── .env.example        # Szablon dla .env
```

### Opis plików

| Plik | Opis |
|------|------|
| `council.py` | Entry point CLI, obsługa argumentów, tryb interaktywny, orkiestracja zapytań |
| `providers.py` | Async klienty HTTP dla providerów (OpenAI, Anthropic, Google, Ollama, LM Studio, AnythingLLM) |
| `analyzers.py` | Analiza wariancji między odpowiedziami, 6 technik debiasingu |
| `config/providers.yaml` | Włączanie/wyłączanie providerów, URL-e, modele, timeouty |
| `config/experts.yaml` | Persony ekspertów z system promptami i triggerami |
| `config/user_model.yaml` | Twój profil - cele, ograniczenia, styl komunikacji |

## Instalacja

```bash
cd cognitive-stack
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edytuj .env i dodaj klucze API
```

## Użycie

```bash
# Podstawowe zapytanie
./council.py "Twoje pytanie"

# Z ekspertem
./council.py "Pytanie" --expert cost_cutter

# Z debiasingiem
./council.py "Pytanie" --debias premortem,counterargs

# Tryb interaktywny
./council.py --interactive

# Lista ekspertów
./council.py --list-experts

# Lista technik debiasingu
./council.py --list-debias
```

## Konfiguracja

### Pliki konfiguracyjne

- `config/user_model.yaml` - Twój profil (cele, ograniczenia, styl komunikacji)
- `config/experts.yaml` - Persony ekspertów
- `config/providers.yaml` - Konfiguracja API (modele, timeouty, włączanie providerów)

### Zmienne środowiskowe (.env)

```bash
# === Cloud providers ===
OPENAI_API_KEY=sk-proj-...
MODEL_NAME_OPENAI=gpt-4o

CLAUDE_API_KEY=sk-ant-...
MODEL_NAME_CLAUDE=claude-sonnet-4-20250514

GEMINI_API_KEY=AIzaSy...
MODEL_NAME_GEMINI=gemini-2.5-pro

# === Lokalne modele ===
LMSTUDIO_API_URL=http://169.254.83.107:1234/v1
LMSTUDIO_API_KEY=local
MODEL_NAME_LM=google/gemma-3-27b

ANYTHING_API_URL=http://169.254.83.107:1234/v1
ANYTHING_API_KEY=local
MODEL_NAME_ANY=qwen3-asteria-14b-128k
```

## Lokalne modele

Cognitive Stack obsługuje lokalne modele przez:
- **Ollama** - natywne API Ollama
- **LM Studio** - OpenAI-compatible API
- **Anything LLM** - OpenAI-compatible API

### Konfiguracja lokalnych modeli

#### 1. Edytuj `.env`

```bash
# Dla LM Studio (ustaw IP hosta, nie localhost jeśli używasz WSL)
LMSTUDIO_API_URL=http://169.254.83.107:1234/v1
LMSTUDIO_API_KEY=local
MODEL_NAME_LM=google/gemma-3-27b

# Dla Anything LLM
ANYTHING_API_URL=http://169.254.83.107:1234/v1
ANYTHING_API_KEY=local
MODEL_NAME_ANY=qwen3-asteria-14b-128k
```

#### 2. Edytuj `config/providers.yaml`

Włącz providera zmieniając `enabled: false` na `enabled: true`:

```yaml
  lmstudio:
    enabled: true  # <- zmień z false na true
    api_key: "${LMSTUDIO_API_KEY:local}"
    model: "${MODEL_NAME_LM:google/gemma-3-27b}"
    base_url: "${LMSTUDIO_API_URL:http://localhost:1234/v1}"
    max_tokens: 4096
    temperature: 0.7
    timeout: 300  # lokalne modele potrzebują więcej czasu
```

#### 3. Dodaj do `default_council`

Na końcu `config/providers.yaml`:

```yaml
default_council:
  - openai
  - anthropic
  - lmstudio  # <- dodaj lokalny provider
```

Lub tylko lokalne modele:

```yaml
default_council:
  - lmstudio
  - anythingllm
```

### Uwaga dla WSL

Jeśli używasz WSL, a LM Studio działa na Windows, użyj IP hosta Windows zamiast `localhost`:

```bash
# Sprawdź IP w PowerShell:
# (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "vEthernet (WSL)").IPAddress

LMSTUDIO_API_URL=http://169.254.83.107:1234/v1
```

## Dostępni eksperci

| Ekspert | Opis |
|---------|------|
| `strategist` | Myślenie długoterminowe, wizja |
| `cost_cutter` | Pragmatyczny, ROI, budżet |
| `security_auditor` | Threat modeling, ryzyka |
| `operator` | SRE, day-2 operations |
| `devils_advocate` | Szuka dziur, kwestionuje założenia |
| `coach` | Czynnik ludzki, motywacja |

## Techniki debiasingu

| Technika | Opis |
|----------|------|
| `premortem` | Co poszło nie tak za rok? |
| `counterargs` | Najsilniejsze kontrargumenty |
| `uncertainty` | Poziomy pewności |
| `assumptions` | Ukryte założenia |
| `reference_class` | Jak to wygląda statystycznie? |
| `change_mind` | Co zmieniłoby zdanie? |

## Changelog

### v1.4.0

**Obsługa dwóch języków (PL/EN):**
- Prompty debiasingowe dostępne po polsku i angielsku
- Etykiety UI (Variance Analysis, Debiasing) w wybranym języku
- Ustawienie języka w `config/user_model.yaml` → `communication_style.preferred_language`

**Kompatybilność z GPT-5.x:**
- Automatyczna detekcja modeli reasoning (`gpt-5*`, `o1*`, `o3*`, `o4*`)
- GPT-5.x: `max_completion_tokens` zamiast `max_tokens`
- GPT-5.x: wyłączenie `temperature` (nieobsługiwane)
- Pełna kompatybilność wsteczna z GPT-4.x i starszymi

### v1.3.0

**Lokalne modele:**
- Dodano obsługę LM Studio (OpenAI-compatible API)
- Dodano obsługę Anything LLM (OpenAI-compatible API)
- Konfigurowalny timeout per-provider dla lokalnych modeli
- Dokumentacja konfiguracji WSL → Windows

### v1.2.1

**Poprawki SonarQube:**
- `_handle_command` zmieniono na funkcję void

### v1.2.0

**Poprawki SonarQube:**
- Usunięto redundantne `json.JSONDecodeError`
- Zrefaktorowano `interactive_mode` - cognitive complexity 64→12
- Zrefaktorowano `_safe_get` - cognitive complexity 19→10
- Wyodrębniono stałą `ERR_EMPTY_RESPONSE` (DRY)
- Wyodrębniono handlery komend do osobnych funkcji
- Dodano `InteractiveState` dataclass

### v1.1.0

**Poprawki bezpieczeństwa:**
- Rozszerzone wzorce sanityzacji kluczy API
- Walidacja maksymalnej długości zapytania
- Górny limit timeout (max 5 minut)

**Poprawki błędów:**
- Fix: mutacja konfiguracji (deepcopy)
- Fix: bezpieczne parsowanie odpowiedzi API
- Fix: zamykanie klientów HTTP
- Retry z exponential backoff
- Google Gemini: natywne `systemInstruction`

**Ulepszenia:**
- Równoległy debiasing
- Connection pooling
- Nowe opcje CLI: `--list-debias`, `--verbose`, `--version`
- Pełne type hints i docstringi
- Obsługa Ctrl+C

### v1.0.0

- Pierwsza wersja

---

# Cognitive Stack - English version

## Project Origin

Project inspired by the **"Synthetic Cognitive Systems"** concept - moving from simple "ask 3 models" to a designed cognitive stack.

**Key philosophy:** Stop treating AI like a chatbot, start treating it like a designed decision-making process.

More about the concept: [LinkedIn - Synthetic Cognitive Systems](https://www.linkedin.com/posts/pawelpszczesny_ask-three-models-llm-council-is-the-first-activity-7399323058169188352-EaBD?utm_source=social_share_send&utm_medium=android_app&rcm=ACoAACUmdFUByw_8om7AOfbbt_Y2whMI-6rmMmY&utm_campaign=share_via)

### Five Levels of the Cognitive Stack:

1. **LLM-Council** - variance as signal (where models agree = higher confidence)
2. **User Model** - user profile (goals, constraints, risk tolerance)
3. **Expert Matching** - matching expert persona to question context
4. **Debiasing Protocols** - forcing critical thinking (pre-mortem, counterarguments)
5. **Intuition as Data** - protocols for hunches and non-obvious signals

## Architecture

```
cognitive-stack/
├── council.py          # Main CLI entry point
├── providers.py        # API clients (OpenAI, Anthropic, Google, Ollama, LM Studio)
├── analyzers.py        # Variance analysis + debiasing techniques
├── config/
│   ├── providers.yaml  # API provider configuration
│   ├── experts.yaml    # Expert persona definitions
│   └── user_model.yaml # User profile
├── .env                # API keys (don't commit!)
└── .env.example        # Template for .env
```

### File Descriptions

| File | Description |
|------|-------------|
| `council.py` | CLI entry point, argument handling, interactive mode, query orchestration |
| `providers.py` | Async HTTP clients for providers (OpenAI, Anthropic, Google, Ollama, LM Studio, AnythingLLM) |
| `analyzers.py` | Variance analysis between responses, 6 debiasing techniques |
| `config/providers.yaml` | Enable/disable providers, URLs, models, timeouts |
| `config/experts.yaml` | Expert personas with system prompts and triggers |
| `config/user_model.yaml` | Your profile - goals, constraints, communication style |

## Installation

```bash
cd cognitive-stack
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and add API keys
```

## Usage

```bash
# Basic query
./council.py "Your question"

# With a specific expert
./council.py "Question" --expert cost_cutter

# With debiasing
./council.py "Question" --debias premortem,counterargs

# Interactive mode
./council.py --interactive

# List experts
./council.py --list-experts

# List debiasing techniques
./council.py --list-debias
```

## Configuration

### Configuration Files

- `config/user_model.yaml` - Your profile (goals, constraints, communication style)
- `config/experts.yaml` - Expert personas
- `config/providers.yaml` - API configuration (models, timeouts, enabling providers)

### Environment Variables (.env)

```bash
# === Cloud providers ===
OPENAI_API_KEY=sk-proj-...
MODEL_NAME_OPENAI=gpt-4o

CLAUDE_API_KEY=sk-ant-...
MODEL_NAME_CLAUDE=claude-sonnet-4-20250514

GEMINI_API_KEY=AIzaSy...
MODEL_NAME_GEMINI=gemini-2.5-pro

# === Local models ===
LMSTUDIO_API_URL=http://169.254.83.107:1234/v1
LMSTUDIO_API_KEY=local
MODEL_NAME_LM=google/gemma-3-27b

ANYTHING_API_URL=http://169.254.83.107:1234/v1
ANYTHING_API_KEY=local
MODEL_NAME_ANY=qwen3-asteria-14b-128k
```

## Local Models

Cognitive Stack supports local models via:
- **Ollama** - native Ollama API
- **LM Studio** - OpenAI-compatible API
- **Anything LLM** - OpenAI-compatible API

### Configuring Local Models

#### 1. Edit `.env`

```bash
# For LM Studio (use host IP, not localhost if using WSL)
LMSTUDIO_API_URL=http://169.254.83.107:1234/v1
LMSTUDIO_API_KEY=local
MODEL_NAME_LM=google/gemma-3-27b

# For Anything LLM
ANYTHING_API_URL=http://169.254.83.107:1234/v1
ANYTHING_API_KEY=local
MODEL_NAME_ANY=qwen3-asteria-14b-128k
```

#### 2. Edit `config/providers.yaml`

Enable the provider by changing `enabled: false` to `enabled: true`:

```yaml
  lmstudio:
    enabled: true  # <- change from false to true
    api_key: "${LMSTUDIO_API_KEY:local}"
    model: "${MODEL_NAME_LM:google/gemma-3-27b}"
    base_url: "${LMSTUDIO_API_URL:http://localhost:1234/v1}"
    max_tokens: 4096
    temperature: 0.7
    timeout: 300  # local models need more time
```

#### 3. Add to `default_council`

At the end of `config/providers.yaml`:

```yaml
default_council:
  - openai
  - anthropic
  - lmstudio  # <- add local provider
```

Or local models only:

```yaml
default_council:
  - lmstudio
  - anythingllm
```

### Note for WSL Users

If using WSL with LM Studio running on Windows, use the Windows host IP instead of `localhost`:

```bash
# Check IP in PowerShell:
# (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "vEthernet (WSL)").IPAddress

LMSTUDIO_API_URL=http://169.254.83.107:1234/v1
```

## Available Experts

| Expert | Description |
|--------|-------------|
| `strategist` | Long-term thinking, vision |
| `cost_cutter` | Pragmatic, ROI, budget |
| `security_auditor` | Threat modeling, risks |
| `operator` | SRE, day-2 operations |
| `devils_advocate` | Finds flaws, questions assumptions |
| `coach` | Human factor, motivation |

## Debiasing Techniques

| Technique | Description |
|-----------|-------------|
| `premortem` | What went wrong a year later? |
| `counterargs` | Strongest counterarguments |
| `uncertainty` | Confidence levels |
| `assumptions` | Hidden assumptions |
| `reference_class` | Statistical comparison |
| `change_mind` | What would change your mind? |

## Changelog

### v1.4.0

**Bilingual support (PL/EN):**
- Debiasing prompts available in Polish and English
- UI labels (Variance Analysis, Debiasing) in selected language
- Language setting in `config/user_model.yaml` → `communication_style.preferred_language`

**GPT-5.x compatibility:**
- Auto-detection of reasoning models (`gpt-5*`, `o1*`, `o3*`, `o4*`)
- GPT-5.x: `max_completion_tokens` instead of `max_tokens`
- GPT-5.x: disabled `temperature` (not supported)
- Full backward compatibility with GPT-4.x and older

### v1.3.0

**Local models:**
- Added LM Studio support (OpenAI-compatible API)
- Added Anything LLM support (OpenAI-compatible API)
- Configurable per-provider timeout for local models
- WSL → Windows configuration documentation

### v1.2.1

**SonarQube fixes:**
- Changed `_handle_command` to void function

### v1.2.0

**SonarQube fixes:**
- Removed redundant `json.JSONDecodeError`
- Refactored `interactive_mode` - cognitive complexity 64→12
- Refactored `_safe_get` - cognitive complexity 19→10
- Extracted `ERR_EMPTY_RESPONSE` constant (DRY)
- Extracted command handlers to separate functions
- Added `InteractiveState` dataclass

### v1.1.0

**Security enhancements:**
- Expanded API key sanitization patterns
- Query max length validation
- Upper timeout limit (max 5 minutes)

**Bug fixes:**
- Fix: configuration mutation (deepcopy)
- Fix: safe API response parsing
- Fix: HTTP client shutdown
- Retry with exponential backoff
- Google Gemini: native `systemInstruction`

**Improvements:**
- Parallel debiasing
- Connection pooling
- New CLI options: `--list-debias`, `--verbose`, `--version`
- Full type hints and docstrings
- Ctrl+C handling

### v1.0.0

- Initial release

---

## License

MIT License - see [LICENSE](LICENSE)