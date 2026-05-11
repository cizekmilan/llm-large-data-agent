#!/usr/bin/env python3

import json
import tiktoken
from colorama import Back, Fore, Style, init

init(autoreset=True)


# === Funkce pro vstup uživatele

def get_user_query(prompt="user_query> "):
    while True:
        try:
            q = input(prompt).strip()
            if q.lower() in ["bye", "exit", "quit", "q"]:
                return None
            if q:
                return q
        except EOFError:
            return None


# === Pomocné funkce pro debug výstup

def estimate_tokens(data, model="gpt-4o-mini"):
    """
    Odhad počtu tokenů pro libovolná data (dict/list/string).
    """
    if not isinstance(data, str):
        data = json.dumps(data, ensure_ascii=False)

    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")

    return len(enc.encode(data))


def sanitize_text(text):
    """
    Očistí text od problematických Unicode znaků (zejména typografických mezer),
    které se sice korektně přenášejí (UTF-8), ale některé terminály je neumí zobrazit
    a vykreslí je jako čtverečky (□).

    Poznámka:
    Nejde o chybu kódování, ale o omezení fontu / terminálu.
    """
    return (
        text
        .replace("\u202f", " ")
        .replace("\u00a0", " ")
    )


def safe_json(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj


def debug_request(input_list, tools, llm_name, bgcolor=Back.BLACK):
    print(bgcolor + Fore.CYAN + f"\n================ REQUEST ({llm_name}) ================")
    safe_input = [safe_json(i) for i in input_list]

    print(bgcolor + Fore.CYAN + "INPUT:")
    print(bgcolor + Fore.CYAN + json.dumps(safe_input, indent=2, ensure_ascii=False))
    print(bgcolor + Fore.CYAN + "\nTOOLS:")
    print(bgcolor + Fore.CYAN + json.dumps(tools, indent=2, ensure_ascii=False))

    # už jen doplním odhad tokenů
    input_tokens = estimate_tokens(safe_input)
    tools_tokens = estimate_tokens(tools)
    total = input_tokens + tools_tokens
    print(Back.WHITE + Fore.RED + f"\nTOKENS_EST: input={input_tokens} + tools={tools_tokens} --> total={total}")


def debug_response(response, llm_name, bgcolor=Back.BLACK):
    print(bgcolor + Fore.GREEN + f"\n================ RESPONSE ({llm_name}) ================")
    safe_output = [safe_json(i) for i in response.output]
    print(bgcolor + Fore.GREEN + json.dumps(safe_output, indent=2, ensure_ascii=False))

    # extra debug – typy itemů
    types = [item.type for item in response.output]
    print(Fore.MAGENTA + f"\nITEM TYPES ({len(types)}): {', '.join(types)}")

    # už jen doplním odhad tokenů
    #output_tokens = estimate_tokens(safe_output)
    #print(Back.WHITE + Fore.RED + f"\nTOKENS_EST (response): output={output_tokens}")
