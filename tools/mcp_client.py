import asyncio
import json
import subprocess
import shutil
from typing import List, Dict, Any, Optional

class MCPClientWrapper:
    """
    Model Context Protocol (MCP) Client Wrapper.
    Enables JARVIS to dynamically discover and invoke external tools and resources
    exposed by MCP servers over stdio or process transport.
    """

    def __init__(self, server_command: str = "npx", server_args: Optional[List[str]] = None):
        self.server_command = server_command
        self.server_args = server_args or ["-y", "@modelcontextprotocol/server-filesystem", "./"]
        self.process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0

    async def connect(self):
        """Starts the MCP server process with stdio pipe transport."""
        # SECURITY HARDENING (Ponytail SEC-06): Verify executable exists before launching
        if not shutil.which(self.server_command):
            print(f"[MCPClient] Binary '{self.server_command}' not found on PATH. Operating in safe offline mock mode.")
            self.process = None
            return

        try:
            self.process = await asyncio.create_subprocess_exec(
                self.server_command,
                *self.server_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            # Initialize MCP session handshake
            await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "JARVIS-MCP-Client", "version": "1.0.0"}
            })
        except Exception as e:
            print(f"[MCPClient] Connection failed (running in offline/mock mode): {e}")
            self.process = None

    async def _send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.process or not self.process.stdin or not self.process.stdout:
            return {"status": "error", "message": "MCP process unavailable"}

        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params
        }
        raw_msg = json.dumps(payload) + "\n"
        self.process.stdin.write(raw_msg.encode("utf-8"))
        await self.process.stdin.drain()

        line = await self.process.stdout.readline()
        if not line:
            return {"status": "error", "message": "No response from MCP server"}
        
        try:
            return json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            return {"status": "error", "message": "Failed to decode MCP JSON-RPC response"}

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Queries the MCP server for available executable tools."""
        if not self.process:
            return [
                {"name": "mcp_filesystem_read", "description": "Read file contents via MCP (Mock)"},
                {"name": "mcp_filesystem_list", "description": "List directory contents via MCP (Mock)"}
            ]
        resp = await self._send_request("tools/list", {})
        if "result" in resp and "tools" in resp["result"]:
            return resp["result"]["tools"]
        return []

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Executes an MCP tool by name with arguments."""
        if not self.process:
            return {"status": "success", "result": f"Simulated MCP execution for {name} with args {arguments}"}
        
        resp = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments
        })
        return resp.get("result", resp)

    async def close(self):
        """Cleanly terminates the MCP server process."""
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except Exception:
                pass
            self.process = None
