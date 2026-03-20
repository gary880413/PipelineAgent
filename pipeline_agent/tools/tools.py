import inspect
from enum import Enum
from typing import Callable, Dict, Any, List, Optional

from pipeline_agent.schemas.schema import Runtime

from pipeline_agent.utils.logger import setup_logger
logger = setup_logger("pipeline_agent.planner")

class DefaultCategory:
    WEB_SCRAPING = "WebScraping"
    DATA_ANALYSIS = "DataAnalysis"
    SYSTEM = "SystemFiles"
    COMMUNICATION = "Communication"
    TEXT_PROCESSING = "TextProcessing" 
    EXTERNAL_SERVICE = "ExternalService" 

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(self, category: DefaultCategory, runtime: Runtime, description: str):
        def decorator(func: Callable):
            sig = inspect.signature(func)
            
            tool_info = {
                "name": func.__name__,
                "category": category,
                "runtime": runtime.value,  
                "description": description,
                "signature": str(sig),
                "callable": func,
                "mcp_schema": None # Native tools do not have this
            }
            self._tools[func.__name__] = tool_info
            return func
        return decorator

    def register_direct(self, 
                        name: str, 
                        category: str, 
                        runtime: str, 
                        description: str, 
                        func: Callable, 
                        mcp_schema: Optional[Dict[str, Any]] = None):
        """
        Directly register a tool into the registry, bypassing the decorator.
        This is intended for external tools (such as MCP) to be dynamically mounted.
        """
        self._tools[name] = {
            "name": name,
            "category": category,
            "runtime": runtime,
            "description": description,
            "callable": func,
            "mcp_schema": mcp_schema # Store the JSON Schema sent from MCP Server, used for Planner visualization in the future
        }
        logger.info(f"🔌 [Registry] Successfully dynamically mounted external tool: {name}")

    def get_tools_by_categories(self, categories: List[str]) -> List[Dict[str, Any]]:
        """For the second stage of the brain: only retrieve tool details of specific categories"""
        return [t for t in self._tools.values() if t["category"] in categories]

    def get_all_categories(self) -> List[str]:
        """For the first stage of the brain: only provide high-level categories"""
        return list(set(t["category"] for t in self._tools.values()))

# Instantiate the global registry
registry = ToolRegistry()
tool = registry.register