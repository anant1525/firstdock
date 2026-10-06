#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""server.py — starter-kit template for a governed MCP tool backend.

`new-tool.sh` copies this file (with TOOL_NAME substituted) into
~/tools/<alias>/server.py, then deploys it as a ConfigMap + Deployment +
Service in `components`, the same shape modaas-docs and demo-tool-backend
use (static/kb/modaas-docs-mcp.yaml, static/reference-impl/demo-tool-backend.yaml).

Stdlib only, deliberately boring, same as the reference backends: enough MCP
(Streamable HTTP, JSON-RPC 2.0) to be a real tool your ToolConfig can front,
and nothing more. Replace `EXAMPLE_TOOL` and the body of `call_tool()` with
your own logic; the JSON-RPC plumbing below does not need to change for a
single-tool backend.

MCP surface:
  POST /      initialize | tools/list | tools/call
  POST /mcp   the same handler (agentgateway's AgentgatewayBackend connects
              with no path; some MCP clients try /mcp first — serving both
              avoids a 404 nobody would diagnose quickly)
  GET  /healthz
"""
#!/usr/bin/env python3

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROTOCOL = "2024-11-05"
SERVER_NAME = os.environ.get("TOOL_NAME", "alarm-get-fault")

TOOLS = [
    {
        "name": "alarm_get_fault",
        "description": """
        Retrieve active telecom network alarms and faults.
        Use this tool whenever the user asks:
        - show alarms
        - active alarms
        - critical alarms
        - major alarms
        - fault status
        - network faults
        - alarm inventory
        - NOC alarms
        """,
        "inputSchema": {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "enum": [
                        "critical",
                        "major",
                        "minor",
                        "warning"
                    ],   
                    "description": "Alarm severity filter"
                }
            }
        }
    }
]


def call_tool(name, args):
    print(f"TOOL CALLED: {name}")
    print(f"ARGS: {args}")
    if name != "alarm_get_fault":
        return {
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": f"unknown tool {name}"
                }
            ]
        }

    severity = (args or {}).get("severity", "critical")

    result = {
        "alarmId": "ALM-1001",
        "severity": severity,
        "networkFunction": "AMF",
        "node": "amf-node-01",
        "description": "N2 Interface Failure",
        "status": "Active"
    }

    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(result, indent=2)
            }
        ]
    }


def handle(req):
    rid = req.get("id")
    method = req.get("method")

    if method == "initialize":
        res = {
            "protocolVersion": PROTOCOL,
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": "1.0.0"
            }
        }

    elif method == "tools/list":
        res = {
            "tools": TOOLS
        }

    elif method == "tools/call":
        p = req.get("params") or {}
        res = call_tool(
            p.get("name"),
            p.get("arguments")
        )

    elif method == "notifications/initialized":
        return None

    elif method == "ping":
        res = {}
    
    else:
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "error": {
                "code": -32601,
                "message": f"method not found: {method}"
            }
        }

    return {
        "jsonrpc": "2.0",
        "id": rid,
        "result": res
    }


class H(BaseHTTPRequestHandler):

    def log_message(self, *args):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()

        try: 
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Mcp-Session-Id", SERVER_NAME)
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):

        if self.path.startswith("/healthz"):
            return self._json(200, {"ok": True})

        # Streamable HTTP GET endpoint expected by Strands MCP client
        if self.path.startswith("/mcp"):
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Mcp-Session-Id", SERVER_NAME)
                self.end_headers()

                self.wfile.write(b": connected\n\n")
                self.wfile.flush()

                while True:
                    time.sleep(15)
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()

            except (BrokenPipeError, ConnectionResetError):
                pass

            return

        return self._json(
            404,
            {"error": f"not found: {self.path}"}
        )

    def do_POST(self):

        # Accept:
        # /
        # /mcp
        # /mcp/alarm-get-fault
        if not (
            self.path == "/" or
            self.path.startswith("/mcp")
        ):
            return self._json(
                404,
                {"error": f"not found: {self.path}"}
            )

        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(
                self.rfile.read(length).decode("utf-8")
            )
        except Exception as e:
            return self._json(
                400,
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": str(e)
                    }
                }
            )
       
        response = handle(req)

        if response is None:
            self.send_response(202)
            self.end_headers()
            return

        return self._json(200, response)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), H).serve_forever()

