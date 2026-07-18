#!/usr/bin/env python3

import json
from openai import OpenAI
import os
from dotenv import load_dotenv
from colorama import Back, Fore, Style, init

# vlastní funkce
from misc import estimate_tokens, debug_request, debug_response


init(autoreset=True)
load_dotenv()

LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL")


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



def transform_tool_output(result, tool_name=None, user_query=None):
    """
    LLM-based reducer:
    - vezme raw tool output
    - vrátí zredukovaný JSON podle user_query
    """
    orig_tokens = estimate_tokens(result)

    # malé payloady neřešíme, většinou spíš nárůst
    #if orig_tokens < 1000:
    #    print(Back.BLACK + Fore.YELLOW + f"\nSKIP TRANSFORM (<1000 tokens): {orig_tokens}")
    #    return result

    client = OpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_API_BASE_URL
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

    response = client.responses.create(
        model=LLM_MODEL,
        input=input_list,
        temperature=0.0,
        top_p=0.0000000000000000000001,
    )

    debug_response(response, "LLM2_REDUCER", Back.BLUE)

    text = response.output_text.strip()

    # pokus o parsování JSON
    try:
        reduced = json.loads(text)
    except Exception:
        # fallback – když model vrátí blbost (nevalidní JSON)
        reduced = {
            "meta": {
                "strategy": "fallback",
                "notes": "Model did not return valid JSON"
            },
            "data": result
        }

    # jen výpis počtu tokenů před a po transformaci
    new_tokens = estimate_tokens(reduced)
    diff = new_tokens - orig_tokens   # pozor: obráceně pro přirozené znaménko
    percent = (diff / orig_tokens * 100) if orig_tokens > 0 else 0
    print(Back.WHITE + Fore.RED +
          f"\nTOKENS CHANGE: {orig_tokens} -> {new_tokens} "
          f"(Δ{diff:+} / {percent:+.1f}%)")

    return reduced
