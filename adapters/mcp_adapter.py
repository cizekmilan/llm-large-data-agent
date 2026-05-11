#!/usr/bin/env python3

from mcp import ClientSession
import logging


class MCPAdapter:
    def __init__(self, server_url, bearer_token=None):
        self.server_url = server_url.rstrip("/")
        self.bearer_token = bearer_token
        self.logger = logging.getLogger(__name__)


    def get_tools(self):
        self.logger.info(
            "MCPAdapter.get_tools() not implemented yet"
        )

        return [], {}


    def call_tool(self, operation, args):
        self.logger.info(
            f"MCPAdapter.call_tool() not implemented yet "
            f"operation={operation}"
        )

        return {
            "error": "MCP adapter not implemented yet"
        }
