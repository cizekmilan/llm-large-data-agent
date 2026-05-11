#!/usr/bin/env python3

import json
from openai import OpenAI
import os
from dotenv import load_dotenv
from colorama import Back, Fore, Style, init
import logging

# vlastní funkce
from misc import estimate_tokens, debug_request, debug_response

init(autoreset=True)
load_dotenv()

LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_NAME = os.getenv("LLM_NAME")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))
LLM_TOP_P = float(os.getenv("LLM_TOP_P", "1.0"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))

logger = logging.getLogger("reducer")


# POZOR:
# Responses API s parametrem "instructions" negarantuje striktní dodržení JSON formátu.
# Model má tendenci vracet Markdown/tabulky/reporty, i když prompt striktně požaduje JSON.
#
# Pro spolehlivé JSON výstupy je spolehlivější použít klasickou zprávu:
# {"role": "system", "content": "..."}
# přímo v inputu konverzace místo samostatného parametru instructions=SYSTEM_PROMPT.
#
# V praxi je role=system výrazně poslušnější pro:
# - validní JSON output
# - structured output
# - zákaz markdownu/tabulek
# - redukční/sumarizační pipeline


SYSTEM_PROMPT = """
You are a data reducer for an AI agent.

IMPORTANT:
The data you process may be used in future steps.
Your output will be used as input for further tool calls.

CRITICAL:
- You MUST NOT invent, infer, or simulate any data.
- You MUST NOT add fields that are not present in the input.
- If some information is missing, leave it missing.
- Never try to complete the answer.

Your task:
- Reduce data size significantly
- Keep only information relevant to the user query OR required for future steps

DISTINGUISH BETWEEN:

1) CONTROL DATA (MUST PRESERVE)
- identifiers used for further tool calls (e.g., customer_id, user_id)
- linking keys between entities
- any fields required as input for other tools

2) PAYLOAD DATA (CAN BE REDUCED)
- large collections (lists of items, logs, tickets, records)
- repeated structures
- verbose text fields

RULES:

ALWAYS PRESERVE:
- identifiers required for further tool calls (e.g., customer_id)
- minimal linking information

FOR LARGE DATASETS:
- DO NOT keep all items
- reduce the number of records (sample, select, or summarize)
- remove unnecessary IDs inside large collections unless explicitly needed
- prefer aggregation (counts, summaries) over full lists

REMOVE:
- redundant fields
- verbose or irrelevant data
- duplicated structures

DO NOT:
- invent missing fields (e.g., payment_status if not provided)
- summarize data that is not present
- create placeholders like "unknown", "N/A", null for missing sections
- assume relationships not explicitly present in the input

IF DATA IS MISSING:
- simply omit it from the output
- do NOT try to complete the response

OUTPUT REQUIREMENTS:
- Return plain JSON text
- Do NOT call tools
- Do NOT use function calling
- Do NOT add explanations outside JSON

Output format:
{
  "meta": {
    "strategy": "<selection | aggregation | summarization | transformation>",
    "notes": "<short explanation of what was kept and why>"
  },
  "data": <reduced data>
}
"""



def transform_tool_output(result, user_query=None):
    """
    LLM-based reducer:
    - vezme raw tool output
    - vrátí zredukovaný JSON podle user_query
    """
    orig_tokens = estimate_tokens(result)  # slouží jen k finálnímu výpočtu "komprese"

    client = OpenAI(
        base_url=LLM_API_BASE_URL,
        api_key=LLM_API_KEY,
        timeout=LLM_TIMEOUT
    )

    user_content = f"""
User query:
{user_query}

Input data:
{json.dumps(result, ensure_ascii=False)}
"""

    input_list = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ]

    debug_request(input_list, None, "LLM2_REDUCER", Back.BLUE)

    try:
        response = client.responses.create(
            model=LLM_NAME,
            #instructions=SYSTEM_PROMPT,
            #input=user_content,
            input=input_list,
            reasoning={"effort": "medium"},  # upported values are model-dependent and can include none, minimal, low, medium, high, and xhigh
            temperature=LLM_TEMPERATURE,
            top_p=LLM_TOP_P
        )
    except Exception as e:
        logger.exception(f"LLM REQUEST FAILED: {e}")
        print(Fore.RED + f"\nLLM ERROR: {e}")


    debug_response(response, "LLM2_REDUCER", Back.BLUE)
    text = response.output_text.strip()

    # pokus o parsování JSON
    try:
        reduced = json.loads(text)
        #TEMP
        logger.info(f"[REDUCER] reduced type={type(reduced)}")

        if isinstance(reduced, dict):
            logger.info(f"[REDUCER] keys={list(reduced.keys())}")

        logger.info(f"[REDUCER] serialized_size={len(json.dumps(reduced, ensure_ascii=False))}")
        logger.info(f"[REDUCER] preview={json.dumps(reduced, ensure_ascii=False)[:1000]}")

    except Exception:
        # fallback - když model vrátí blbost (nevalidní JSON)
        logger.warn(f"[REDUCER] Fallback! Model did not return valid JSON")
        reduced = {
            "meta": {
                "strategy": "fallback",
                "notes": "Model did not return valid JSON"
            },
            "data": result
        }

    # jen výpis počtu tokenů před, po transformaci a výpočet úspory
    new_tokens = estimate_tokens(reduced)
    diff = new_tokens - orig_tokens   # pozor: obráceně pro přirozené znaménko
    percent = (diff / orig_tokens * 100) if orig_tokens > 0 else 0

    print(Back.WHITE + Fore.RED +
          f"\nTOKEN CHANGE: {orig_tokens} -> {new_tokens} "
          f"(Δ{diff:+} / {percent:+.1f}%)")
    logger.info(f"TOKEN CHANGE: {orig_tokens} -> {new_tokens} (Δ{diff:+} / {percent:+.1f}%)")

    return reduced
