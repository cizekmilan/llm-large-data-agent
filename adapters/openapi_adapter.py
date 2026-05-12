#!/usr/bin/env python3

import requests
import logging


class OpenAPIAdapter:
    def __init__(self, base_api_url, bearer_token=None):
        self.base_api_url = base_api_url.rstrip("/")
        self.openapi_url = f"{self.base_api_url}/openapi.json"
        self.bearer_token = bearer_token

        self.logger = logging.getLogger(__name__)


    def get_tools(self):
        # načtu si openapi.json schéma
        spec = requests.get(self.openapi_url, timeout=10).json()

        tools = []        # definice funkcí pro LLM (neobsahuje vyloučené parametry)
        operations = {}   # metadata pro executor (plná informace, včetně pagination/meta)

        # parametry, které nechci vystavovat LLM (interní řízení)
        LLM_EXCLUDED_PARAMS = {"limit", "offset", "meta_only"}

        for path, methods in spec.get("paths", {}).items():
            for method, op in methods.items():
                name = op.get("operationId")
                if not name:
                    continue

                description = op.get("description", "")

                # 1) NASBÍRÁNÍ PARAMETRŮ (query, path, body)
                properties = {}
                required = []

                # query + path parametry
                for p in op.get("parameters", []):
                    pname = p["name"]

                    properties[pname] = {
                        **p.get("schema", {"type": "string"}),
                        "description": p.get("description", "")
                    }

                    if p.get("required"):
                        required.append(pname)

                # requestBody (JSON)
                if "requestBody" in op:
                    content = op["requestBody"].get("content", {})
                    if "application/json" in content:
                        schema = content["application/json"].get("schema", {})

                        properties.update(schema.get("properties", {}))
                        required.extend(schema.get("required", []))

                # 2) DETEKCE SCHOPNOSTÍ ENDPOINTU (pro executor)
                param_names = set(properties.keys())

                pagination_supported = "limit" in param_names and "offset" in param_names
                meta_supported = "meta_only" in param_names

                # 3) FILTRACE PARAMETRŮ PRO LLM - LLM nesmí vidět pagination ani meta_only
                llm_properties = {
                    k: v for k, v in properties.items()
                    if k not in LLM_EXCLUDED_PARAMS
                }

                llm_required = [
                    r for r in required
                    if r not in LLM_EXCLUDED_PARAMS
                ]

                # 4) TOOLS PRO LLM - pouze business parametry
                tools.append({
                    "type": "function",
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": llm_properties,
                        "required": list(set(llm_required)),
                        "additionalProperties": False  # LLM nesmí vymýšlet nové parametry
                    }
                })

                # 5) OPERACE PRO EXECUTOR - včetně rozšiřujících metadat
                operations[name] = {
                    "method": method.upper(),
                    "path": path,
                    # schopnosti endpointu
                    "pagination": pagination_supported,
                    "meta_supported": meta_supported,
                }

        return tools, operations


    def call_tool(self, operation, args):
        method = operation["method"]
        path = operation["path"]

        url = self.base_api_url + path

        headers = {
            "Accept": "application/stis+json;version=1"
        }

        if self.bearer_token:
            headers["Authorization"] = (f"Bearer {self.bearer_token}")

        try:
            if method == "GET":
                r = requests.get(url, params=args, headers=headers, timeout=10)
                self.logger.info(f"API CALL: {method} {r.url}")
            elif method == "POST":
                r = requests.post(url, json=args, headers=headers, timeout=10)
                self.logger.info(f"API CALL: {method} {url} body={args}")
            else:
                self.logger.error(f"API CALL: Unsupported method {method}")
                return {"error": f"Unsupported method {method}"}

            r.raise_for_status()
            return r.json()

        except Exception as e:
            self.logger.error(f"API ERROR: {method} {url} args={args} error={e}")
            return {"error": str(e)}
