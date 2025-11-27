# Cognitive Stack - Polish version (English version below)

CLI do orkiestracji wielu modeli LLM z analizą wariancji i protokołami debiasingu.

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

- `config/user_model.yaml` - Twój profil (cele, ograniczenia, styl komunikacji)
- `config/experts.yaml` - Persony ekspertów
- `config/providers.yaml` - Konfiguracja API (modele, timeouty)

## Dostępni eksperci

- `strategist` - myślenie długoterminowe
- `cost_cutter` - pragmatyczny, ROI
- `security_auditor` - threat modeling
- `operator` - SRE, day-2 operations
- `devils_advocate` - szuka dziur
- `coach` - czynnik ludzki

## Techniki debiasingu

- `premortem` - co poszło nie tak za rok?
- `counterargs` - najsilniejsze kontrargumenty
- `uncertainty` - poziomy pewności
- `assumptions` - ukryte założenia
- `reference_class` - jak to wygląda statystycznie?
- `change_mind` - co zmieniłoby zdanie?

## Changelog

### v1.2.1

**Poprawki SonarQube:**
- `_handle_command` zmieniono na funkcję void (usunięto zbędny return zawsze zwracający True)

### v1.2.0

**Poprawki SonarQube:**
- Usunięto redundantne `json.JSONDecodeError` (dziedziczy z `ValueError`)
- Zrefaktorowano `interactive_mode` - cognitive complexity 64→12
- Zrefaktorowano `_safe_get` - cognitive complexity 19→10
- Wyodrębniono stałą `ERR_EMPTY_RESPONSE` (DRY)
- Wyodrębniono handlery komend do osobnych funkcji
- Dodano `InteractiveState` dataclass dla stanu sesji

### v1.1.0

**Poprawki bezpieczeństwa:**
- Rozszerzone wzorce sanityzacji kluczy API (obsługa `sk-proj-*`)
- Walidacja maksymalnej długości zapytania
- Górny limit timeout (max 5 minut)

**Poprawki błędów:**
- Fix: mutacja konfiguracji przy tworzeniu providerów (używa deepcopy)
- Fix: bezpieczne parsowanie odpowiedzi API (brak KeyError przy zmianie formatu)
- Fix: prawidłowe zamykanie klientów HTTP po zakończeniu
- Dodano logikę retry z exponential backoff
- Google Gemini: użycie natywnego `systemInstruction` zamiast workaroundu

**Ulepszenia:**
- Równoległy debiasing (szybsze wykonanie)
- Ponowne użycie połączeń HTTP (connection pooling)
- Lepsze komunikaty błędów
- Nowe opcje CLI: `--list-debias`, `--verbose`, `--version`
- Pełne type hints i docstringi
- Obsługa Ctrl+C w trybie interaktywnym

### v1.0.0

- Pierwsza wersja

# Cognitive Stack - English version

CLI for orchestrating multiple LLM models with variance analysis and debiasing protocols.

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

* `config/user_model.yaml` – Your profile (goals, constraints, communication style)
* `config/experts.yaml` – Expert personas
* `config/providers.yaml` – API configuration (models, timeouts)

## Available Experts

* `strategist` – long-term thinking
* `cost_cutter` – pragmatic, ROI-focused
* `security_auditor` – threat modeling
* `operator` – SRE, day-2 operations
* `devils_advocate` – finds flaws
* `coach` – human factor

## Debiasing Techniques

* `premortem` – what went wrong a year later?
* `counterargs` – strongest counterarguments
* `uncertainty` – confidence levels
* `assumptions` – hidden assumptions
* `reference_class` – statistical comparison
* `change_mind` – what would change your mind?

## Changelog

### v1.2.1

**SonarQube fixes:**

* Changed `_handle_command` to void function (removed redundant return always returning True)

### v1.2.0

**SonarQube fixes:**

* Removed redundant `json.JSONDecodeError` (inherits from `ValueError`)
* Refactored `interactive_mode` - cognitive complexity 64→12
* Refactored `_safe_get` - cognitive complexity 19→10
* Extracted `ERR_EMPTY_RESPONSE` constant (DRY)
* Extracted command handlers to separate functions
* Added `InteractiveState` dataclass for session state

### v1.1.0

**Security enhancements:**

* Expanded sanitization patterns for API keys (including `sk-proj-*`)
* Query max length validation
* Upper timeout limit (max 5 minutes)

**Bug fixes:**

* Fix: configuration mutation when creating providers (now using deepcopy)
* Fix: safe API response parsing (no KeyError on format change)
* Fix: proper HTTP client shutdown after execution
* Added retry logic with exponential backoff
* Google Gemini: using native `systemInstruction` instead of workaround

**Improvements:**

* Parallel debiasing (faster execution)
* HTTP connection pooling (reused connections)
* Better error messages
* New CLI options: `--list-debias`, `--verbose`, `--version`
* Full type hints and docstrings
* Ctrl+C handling in interactive mode

### v1.0.0

* Initial release
