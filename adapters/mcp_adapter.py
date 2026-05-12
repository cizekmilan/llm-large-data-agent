#!/usr/bin/env python3

import requests
#from mcp import ClientSession -- zatím netřeba, jdu nejjednodušší synchronní cestou přes requests
import logging


class MCPAdapter:
    """
    Adapter for MCP-based tool providers.

    Responsibilities:
    - initialize MCP session
    - discover MCP tools
    - generate LLM tool schemas
    - execute MCP JSON-RPC tool calls
    """

    LLM_EXCLUDED_PARAMS = {"limit", "offset", "meta_only"}

    def __init__(self, server_url, bearer_token=None):
        self.server_url = server_url.rstrip("/")
        self.bearer_token = bearer_token

        self.logger = logging.getLogger(__name__)

        self.session_id = None
        self.request_id = 1

        self._initialize_session()


    def _headers(self):
        headers = {
            "Content-Type": "application/json"
        }

        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        return headers


    def _next_id(self):
        self.request_id += 1
        return self.request_id


    def _request(self, payload):
        r = requests.post(
            self.server_url,
            json=payload,
            headers=self._headers(),
            timeout=60
        )

        r.raise_for_status()
        return r.json()


    def _initialize_session(self):
        self.logger.info("Initializing MCP session...")

        payload = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {
                    "name": "llm-large-data-agent",
                    "version": "1.0"
                }
            }
        }

        r = requests.post(
            self.server_url,
            json=payload,
            headers=self._headers(),
            timeout=30
        )

        r.raise_for_status()
        self.session_id = r.headers.get("Mcp-Session-Id")

        if not self.session_id:
            raise RuntimeError("Failed to obtain MCP session id")

        self.logger.info(f"MCP session initialized session_id={self.session_id}")

        # initialized notification
        requests.post(
            self.server_url,
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            },
            headers=self._headers(),
            timeout=30
        )


    def get_tools(self):
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {}
        }

        response = self._request(payload)

        tools = []
        operations = {}

        for tool in response["result"]["tools"]:

            name = tool["name"]

            description = tool.get("description", "")
            schema = tool.get("inputSchema", {})

            properties = schema.get("properties", {})
            required = schema.get("required", [])

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
                "name": name,
                "pagination": pagination_supported,
                "meta_supported": meta_supported,
            }

        return tools, operations


    def call_tool(self, operation, args):
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": operation["name"],
                "arguments": args
            }
        }

        return self._request(payload)
