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
                "mcp_schema": None # 原生工具沒有這個
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
        直接將工具寫入註冊表，繞過裝飾器。專供外部工具 (如 MCP) 動態掛載使用。
        """
        self._tools[name] = {
            "name": name,
            "category": category,
            "runtime": runtime,
            "description": description,
            "callable": func,
            "mcp_schema": mcp_schema # 儲存 MCP Server 傳來的 JSON Schema，未來給 Planner 畫圖用
        }
        logger.info(f"🔌 [Registry] 成功動態掛載外部工具: {name}")

    def get_tools_by_categories(self, categories: List[str]) -> List[Dict[str, Any]]:
        """給大腦第二階段使用的：只撈出特定類別的工具詳情"""
        return [t for t in self._tools.values() if t["category"] in categories]

    def get_all_categories(self) -> List[str]:
        """給大腦第一階段使用的：只提供高階目錄"""
        return list(set(t["category"] for t in self._tools.values()))

# 實例化全域註冊表
registry = ToolRegistry()
tool = registry.register