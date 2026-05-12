#!/usr/bin/env python3

import logging
import requests


class OpenAPIAdapter:
    """
    Adapter for OpenAPI-based tool providers.

    Responsibilities:
    - parse openapi.json
    - generate LLM tool schemas
    - generate internal executor metadata
    - execute REST API calls
    """

    LLM_EXCLUDED_PARAMS = {"limit", "offset", "meta_only"}

    def __init__(self, base_api_url, bearer_token=None):
        self.base_api_url = base_api_url.rstrip("/")
        self.openapi_url = f"{self.base_api_url}/openapi.json"
        self.bearer_token = bearer_token

        self.logger = logging.getLogger(__name__)


    def _headers(self):
        headers = {
            "Accept": "application/stis+json;version=1"
        }

        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        return headers


    def get_tools(self):
        spec = requests.get(self.openapi_url, timeout=10).json()

        tools = []
        operations = {}

        for path, methods in spec.get("paths", {}).items():
            for method, op in methods.items():

                name = op.get("operationId")
                if not name:
                    continue

                description = op.get("description", "")

                properties = {}
                required = []

                # query + path params
                for p in op.get("parameters", []):
                    pname = p["name"]
                    properties[pname] = {
                        **p.get("schema", {"type": "string"}),
                        "description": p.get("description", "")
                    }

                    if p.get("required"):
                        required.append(pname)

                # requestBody
                if "requestBody" in op:
                    content = op["requestBody"].get("content", {})

                    if "application/json" in content:
                        schema = content["application/json"].get("schema", {})
                        properties.update(schema.get("properties", {}))
                        required.extend(schema.get("required", []))

                # capability detection
                param_names = set(properties.keys())

                pagination_supported = "limit" in param_names and "offset" in param_names
                meta_supported = "meta_only" in param_names

                # LLM filtering
                llm_properties = {
                    k: v for k, v in properties.items()
                    if k not in self.LLM_EXCLUDED_PARAMS
                }

                llm_required = [
                    r for r in required
                    if r not in self.LLM_EXCLUDED_PARAMS
                ]

                # LLM tool schema
                tools.append({
                    "type": "function",
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": llm_properties,
                        "required": list(set(llm_required)),
                        "additionalProperties": False
                    }
                })

                # executor metadata
                operations[name] = {
                    "method": method.upper(),
                    "path": path,
                    "pagination": pagination_supported,
                    "meta_supported": meta_supported,
                }

        return tools, operations


    def call_tool(self, operation, args):
        method = operation["method"]
        path = operation["path"]
        url = self.base_api_url + path

        try:
            if method == "GET":
                r = requests.get(
                    url,
                    params=args,
                    headers=self._headers(),
                    timeout=10
                )

                self.logger.info(f"API CALL: {method} {r.url}")

            elif method == "POST":
                r = requests.post(
                    url,
                    json=args,
                    headers=self._headers(),
                    timeout=10
                )

                self.logger.info(f"API CALL: {method} {url} body={args}")

            else:
                self.logger.error(f"Unsupported method: {method}")
                return {"error": f"Unsupported method {method}"}

            r.raise_for_status()
            return r.json()

        except Exception as e:
            self.logger.error(
                f"API ERROR: method={method} "
                f"url={url} args={args} error={e}"
            )

            return {"error": str(e)}
