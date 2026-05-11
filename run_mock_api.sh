#!/bin/bash

# author Milan Cizek <milan.cizek@starnet.cz>
# rel. 2025-11-26

PY_ENV_NAME=".llm-venv"

# Zabraňuje pokusům o hardlinkování při práci s nástrojem uv (např. při instalaci balíčků),
# které často selhávají, pokud cache a virtuální prostředí leží na různých filesystémech.
# Nastaví režim kopírování jako výchozí a potlačí tím warningy o "Failed to hardlink files".
export UV_LINK_MODE=copy

# kontrola, jestli venv prostředí existuje a jestli je platné (nebylo přesunuto do jiného umístění)
if [ -d "$PY_ENV_NAME" ]; then
    if [ -f "$PY_ENV_NAME/bin/activate" ]; then

        # testuje, zda activate funguje tím, že ho spustí v subshellu (abych si nepřepsal proměnné - PATH aj.)
        # funguje univerzálně ('python -m venv', 'uv venv' a 'uv python install')
        VENV_PATH=$( bash -c "source '$PY_ENV_NAME/bin/activate' >/dev/null 2>&1 && echo \"\$VIRTUAL_ENV\"" )

        if [ -z "$VENV_PATH" ] || [ ! -d "$VENV_PATH" ]; then
            echo "Prostředí je neplatné (špatné cesty v activate nebo přesunuté). Mažu..."
            # odstraním a později se vytvoří znovu
            rm -rf "$PY_ENV_NAME"
        else
            # prostředí je konzistentní, žádná akce
            :
        fi
    else
        echo "Soubor activate nenalezen, prostředí není konzistentní. Vytvářím znovu..."
        rm -rf "$PY_ENV_NAME"
    fi
fi

# pokud virtuální prostředí neexistuje, vytvoř ho
if [ ! -d "$PY_ENV_NAME" ]; then
    # POZOR: uv venv zde nepoužívat!
    # uv nevytváří klasické Python venv – používá vlastní interní runtime v ~/.local/share/uv/python/..., který má prioritu v PATH i sys.path.
    # Dochází pak k míchání modulů mezi uv Pythonem a skutečným venv:
    #  - torch se načítá z uv runtime a ztrácí CUDA podporu
    #  - faster-whisper se importuje v jiné verzi než je nainstalovaná
    #  - WhisperX pak padá na nekompatibilitě API
    # Pro ML projekty (torch, CTranslate2, CUDA, WhisperX) je nutné použít klasické venv přes: python3.12 -m venv <dir>.

    #uv venv --python 3.12 "$PY_ENV_NAME" --seed
    python3.12 -m venv "$PY_ENV_NAME"
else
    echo "Virtuální prostředí $PY_ENV_NAME již existuje, přeskočeno vytvoření."
fi


# aktivace prostředí
source "./$PY_ENV_NAME/bin/activate"

  # případná aktualizace
  #pip install --upgrade pip

  # instalace potřebných balíčků a závislostí
  #pip install -r requirements.txt

  uvicorn mock_api:app --port 9001 --reload

# deaktivace prostředí
deactivate
