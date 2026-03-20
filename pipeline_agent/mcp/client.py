import asyncio
from contextlib import AsyncExitStack
from typing import Dict, Any, Optional

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

from pipeline_agent.tools.tools import registry, DefaultCategory
from pipeline_agent.schemas.schema import Runtime
from pipeline_agent.exceptions import MCPConnectionError, MCPCallError

from pipeline_agent.utils.logger import setup_logger
logger = setup_logger("pipeline_agent.planner")

class MCPClientManager:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.sessions: Dict[str, ClientSession] = {}

    async def connect_and_register(
        self, 
        server_name: str, 
        command: str, 
        args: list[str],
        override_runtime: Optional[Runtime] = None,
        category: str = DefaultCategory.EXTERNAL_SERVICE  # 🌟 NEW: Allow developers to define the business category for this MCP
    ):
        logger.info(f"🔄 [MCP] Starting server '{server_name}': {command} {' '.join(args)}")
        
        server_params = StdioServerParameters(command=command, args=args)
        
        try:
            stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
            read, write = stdio_transport
            
            session = await self.exit_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            
            self.sessions[server_name] = session
            
            response = await session.list_tools()
            tools = response.tools
            logger.info(f"✅ [MCP] Successfully connected to '{server_name}', found {len(tools)} available tools (category: {category}).")
            
            for tool in tools:
                # 🌟 Pass category to the underlying registration logic
                self._register_mcp_tool(server_name, session, tool, override_runtime, category)
                
        except Exception as e:
            logger.error(f"❌ [MCP] Failed to connect to '{server_name}': {str(e)}")

    def _register_mcp_tool(
        self, 
        server_name: str, 
        session: ClientSession, 
        tool: Any,
        override_runtime: Optional[Runtime],
        category: str  # 🌟 Receive category
    ):
        unique_tool_name = f"{server_name}_{tool.name}"
        actual_runtime = override_runtime.value if override_runtime else Runtime.EXTERNAL_MCP.value

        async def mcp_proxy_func(**kwargs) -> str:
            logger.info(f"   [MCP I/O] Calling remote tool: {unique_tool_name} (assigned to {actual_runtime.upper()} resource pool)")
            
            result = await session.call_tool(tool.name, arguments=kwargs)
            text_outputs = [content.text for content in result.content if content.type == "text"]
            
            if result.isError:
                error_msg = "\n".join(text_outputs)
                raise MCPCallError(f"MCP Server Error ({unique_tool_name}): {error_msg}")
                
            return "\n".join(text_outputs)

        registry.register_direct(
            name=unique_tool_name,
            category=category, # 🌟 Write the developer-defined category!
            runtime=actual_runtime,
            description=f"[Provided by {server_name}] {tool.description or 'No description'}",
            func=mcp_proxy_func,
            mcp_schema=tool.inputSchema 
        )

    async def close_all(self):
        await self.exit_stack.aclose()
        logger.info("🛑 [MCP] All external connections have been safely closed.")