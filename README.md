# Cognitive Stack

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
