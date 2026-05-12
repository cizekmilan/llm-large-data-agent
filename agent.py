#!/usr/bin/env python3

# v4: oddělení OpenAPI (sestavení toolů, volání) do adaptéru příprava pro paralelní MCP adaptér
# v3: přesun logiky stránkování z LLM do kódu, meta data, ošetření výjimek
# v2: přidává možnost ptát se opakovaně a drží v kontextu předešlou konverzaci (krátkodobá + dlouhodobá paměť)

import requests
import json
from openai import OpenAI, BadRequestError
import os
from dotenv import load_dotenv
from colorama import Back, Fore, Style, init
from pathlib import Path
from datetime import datetime
import logging
import math

# vlastní funkce
from adapters.openapi_adapter import OpenAPIAdapter
from adapters.mcp_adapter import MCPAdapter
from reducer import transform_tool_output
from misc import get_user_query, estimate_tokens, sanitize_text, debug_request, debug_response

# References:
#   https://developers.openai.com/api/docs/guides/function-calling
#   https://developers.openai.com/api/docs/guides/migrate-to-responses
#   https://developers.openai.com/api/docs/guides/reasoning

init(autoreset=True)
load_dotenv()

LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_NAME = os.getenv("LLM_NAME")
LLM_MAX_CONTEXT = int(os.getenv("LLM_MAX_CONTEXT", "200000"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))
LLM_TOP_P = float(os.getenv("LLM_TOP_P", "1.0"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
LLM_CONTEXT_UTILIZATION = float(os.getenv("LLM_CONTEXT_UTILIZATION", "0.25"))
LOG_DIR = os.getenv("LOG_DIR", "logs")

BASE_API_URL = os.getenv("BASE_API_URL", "http://127.0.0.1:9001")
BASE_API_TOKEN = os.getenv("BASE_API_TOKEN")

MCP_URL = os.getenv("MCP_URL")
MCP_TOKEN = os.getenv("MCP_TOKEN")


Path(LOG_DIR).mkdir(exist_ok=True)
log_filename = (f"{LOG_DIR}/debug_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8")
    ]
)

logger = logging.getLogger("agent")
#logging.getLogger("httpx").setLevel(logging.WARNING)
#logging.getLogger("openai").setLevel(logging.WARNING)


client = OpenAI(
    base_url=LLM_API_BASE_URL,
    api_key=LLM_API_KEY,
    timeout=LLM_TIMEOUT
)


# tools = definice funkcí pro LLM (název, popis, parametry), tedy ve formátu, kterému LLM dobře rozumí
# operations = využívám zde v orchestraci pro reálné volání toolu
#adapter = OpenAPIAdapter(BASE_API_URL, BASE_API_TOKEN)  # pro OpenAPI
adapter = MCPAdapter(MCP_URL, MCP_TOKEN)  # pro MCP
tools, operations = adapter.get_tools()


# === definice PROMPT

SYSTEM_PROMPT = """
You are an assistant that MUST use tools to answer questions.

CRITICAL RULES:
- NEVER invent or guess any data
- If you do not have data, ALWAYS call a tool
- If a specific tool exists for the requested data, you MUST use that tool instead of inferring from other data
- Call ONLY ONE tool at a time
- After calling a tool, WAIT for result
- DO NOT simulate API responses

You are NOT allowed to answer from your own knowledge.

- Answer in Czech language.
- Use Markdown formatting.
"""


# === USER CHAT LOOP

# dlouhodobá paměť
#conversation  = []  # pro test s instructions=SYSTEM_PROMPT
conversation  = [
    {"role": "system", "content": SYSTEM_PROMPT},
]

while True:
    user_query = get_user_query()

    if user_query is None:
        print("Bye!")
        exit()

    logger.info(f"==== [NEW QUERY] {user_query}")

    # 1) přidám user dotaz do dlouhodobé paměti
    conversation.append({"role": "user", "content": user_query})

    # 2) vytvořím pracovní kontext pro agenta - krátkodobá (pracovní) paměť
    input_list = conversation.copy()

    # === AGENT LOOP
    MAX_STEPS = 20

    for step in range(MAX_STEPS):
        print(f"\n=== STEP {step+1} ===")
        logger.info(f"--- loop started, step {step+1}")

        debug_request(input_list, tools, "LLM1")

        try:
            response = client.responses.create(
                model=LLM_NAME,
                #instructions=SYSTEM_PROMPT,
                input=input_list,
                reasoning={"effort": "medium"},  # upported values are model-dependent and can include none, minimal, low, medium, high, and xhigh
                tools=tools,
                temperature=LLM_TEMPERATURE,
                top_p=LLM_TOP_P
            )
        except BadRequestError as e:
            logger.error(f"LLM REQUEST FAILED: {e}")

            if "max_model_len" in str(e):
                logger.exception("CONTEXT WINDOW EXCEEDED")
                print(Fore.RED + "\nERROR: Kontext modelu byl překročen.")
                break
            raise
        except Exception as e:
            logger.exception(f"LLM REQUEST FAILED: {e}")
            print(Fore.RED + f"\nLLM ERROR: {e}")


        tool_called = False
        debug_response(response, "LLM1")

        # model může teoreticky vrátit více function_call položek (přestože prompt říká "Call ONLY ONE"),
        # cyklus by je i tak postupně všechny zpracoval iterací přes response.output
        for item in response.output:
            if item.type == "function_call":
                # model se rozhodl, že chce zavolat tool
                # typů je více - např. function_call, function_call_output, message, reasoning, ...
                tool_called = True

                name = item.name
                args = json.loads(item.arguments)

                logger.info(f"LLM TOOL SELECTED: {name}, [ARGS: {args}]")
                print(Fore.YELLOW + f"\n--- TOOL CALL ---")
                print(Fore.YELLOW + f"{name}({args})")

                # 1. uložit function_call do historie
                # input_list.append(item) -- zbytečně plné metadat
                # MINIMAL function_call -- minimalistická verze
                input_list.append({
                    "type": "function_call",
                    "name": item.name,
                    "arguments": item.arguments,
                    "call_id": item.call_id
                })

                if name not in operations:
                    # model se rozhodl zavolat tool/API, které neexistuje
                    logger.error("UNKNOWN TOOL SELECTED: {name}")
                    result = {"error": f"Unknown tool {name}"}
                else:
                    # volání API
                    op = operations[name]
                    if op["meta_supported"] and op["pagination"]:
                        # end-point podporuje zjištění velikosti a stránkování
                        logger.info("API end-point supports metadata & pagination")

                        # zjistím velikost dat a počet
                        meta = adapter.call_tool(op, {**args, "meta_only": True})
                        data_path = meta.get("data_path", "items")
                        total_tokens = meta.get("tokens_estimation", 0)  # jak objemná jsou data vrácená tool callem?
                        total_items = meta.get("total_items", 0)

                        logger.info(f"[META] total_items={total_items}, total_tokens_est={total_tokens}")

                        # výpočet limitu (kolik položek se vejde do jednoho chunku)
                        CHUNK_BUDGET = int(LLM_MAX_CONTEXT * LLM_CONTEXT_UTILIZATION)

                        if total_items == 0:
                            # na endpointu nejsou žádná data (edge case)
                            logger.info("[STRATEGY] EMPTY DATASET")
                            result = []
                        elif total_tokens < CHUNK_BUDGET:
                            # na endpointu je málo dat, vše se zvládne jedním chunkem (netřeba stránkovat)
                            logger.info("[STRATEGY] SINGLE CALL (no paging)")
                            result = adapter.call_tool(op, args)
                        else:
                            # na endpointu je málo dat, bude se stránkovat ...
                            logger.info("[STRATEGY] PAGING ACTIVATED")

                            # průměrná velikost jedné položky v odpovědi
                            avg_tokens_per_item = total_tokens / total_items

                            # kolik položek se vejde do jednoho LLM zpracování
                            limit = int(CHUNK_BUDGET / avg_tokens_per_item)
                            limit = max(1, limit)  # minimálně 1

                            logger.info(f"[CHUNKING] one chunk budget={CHUNK_BUDGET} tokens")
                            logger.info(f"[CHUNKING] avg_tokens_per_item={avg_tokens_per_item:.2f}")
                            logger.info(f"[CHUNKING] items count in one chunk: limit={limit}")

                            total_pages = math.ceil(total_items / limit)
                            logger.info(f"[CHUNKING] total pages: {total_pages}")

                            # PAGING a postupné zpracování všech chnků
                            partial_results = []

                            for offset in range(0, total_items, limit):
                                page_number = (offset // limit) + 1
                                page = adapter.call_tool(op, {**args, "offset": offset, "limit": limit})

                                current = page
                                for key in data_path.split("."):
                                    current = current.get(key, {}) if isinstance(current, dict) else {}
                                items = current if isinstance(current, list) else []

                                logger.info(f"[PAGE {page_number}/{total_pages}] offset={offset} limit=items={limit}")

                                # redukce jednoho chunku
                                logger.info(f"[PAGE {page_number}/{total_pages}] context reduction -> transformation function (summarization/agregation/selection/...)")
                                partial = transform_tool_output(items, user_query=user_query)
                                partial_results.append(partial)

                            # sloučení všech partial výsledků
                            logger.info(f"merging partial results into one ...")
                            result = transform_tool_output(partial_results, user_query=user_query)

                    else:
                      # end-point nepodporuje stránkování, neřeším a volám rovnou
                      logger.info("API end-point without metadata (pagination) support")
                      result = adapter.call_tool(operations[name], args)


                print(Fore.YELLOW + "--- TOOL RESULT ---")
                print(Fore.YELLOW + json.dumps(result, indent=2, ensure_ascii=False))


                # 2. pak function_call_output
                input_list.append({
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": json.dumps(result)
                })

        if not tool_called:
            final_answer = sanitize_text(response.output_text)
            logger.info(f"FINAL ANSWER FROM LLM")

            print(Back.YELLOW + Fore.BLACK + "\n=== FINAL ANSWER ===")
            print(Fore.WHITE + f"\nQUERY: {user_query}\n")
            print(Fore.WHITE + final_answer)

            # 3) uložím jen finální odpověď do conversation (dlouhodobé paměti)
            conversation.append({
                "role": "assistant",
                "content": final_answer
            })
            break

    else:
        logger.error(f"Reached max steps ({MAX_STEPS}) without final answer")
        print("\nReached max steps without final answer")


# NOTE:
# Model může teoreticky v jedné odpovědi vrátit více function_call položek.
# API to umožňuje (response.output může obsahovat více tool callů).
#
# Nicméně v tomto konkrétním setupu je to nepravděpodobné, protože:
# - SYSTEM_PROMPT explicitně říká: "Call ONLY ONE tool at a time"
# - a také: "After calling a tool, WAIT for result"
#
# => Model je tímto veden k sekvenčnímu chování (1 tool → výsledek → další krok).
#
# Přesto kód iteruje přes všechny function_call položky,
# aby byl robustní i pro jiné modely nebo změnu promptu.
