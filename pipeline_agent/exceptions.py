# 檔案路徑: pipeline_agent/exceptions.py

class PipelineAgentError(Exception):
    """PipelineAgent 的基礎例外類別，所有套件內的錯誤都應該繼承它"""
    pass

# ==========================================
# 🧠 Planner (大腦) 相關的錯誤
# ==========================================
class PlannerError(PipelineAgentError):
    """大腦規劃階段發生的錯誤"""
    pass

class RoutingError(PlannerError):
    """第一階段路由找不到合適的工具類別時觸發"""
    pass

class BlueprintGenerationError(PlannerError):
    """第二階段生成 DAG 藍圖失敗 (例如 LLM 回傳格式錯誤) 時觸發"""
    pass

# ==========================================
# ⚙️ Engine (引擎) 相關的錯誤
# ==========================================
class EngineError(PipelineAgentError):
    """引擎執行階段發生的基礎錯誤"""
    pass

class DependencyResolutionError(EngineError):
    """依賴解析失敗 (例如找不到上一個節點的輸出) 時觸發"""
    pass

class ToolExecutionError(EngineError):
    """單一工具 (Tool) 執行時發生崩潰時觸發"""
    def __init__(self, task_id: str, tool_name: str, original_error: Exception):
        self.task_id = task_id
        self.tool_name = tool_name
        self.original_error = original_error
        super().__init__(f"任務 '{task_id}' (工具: {tool_name}) 執行失敗: {str(original_error)}")

# ==========================================
# 🌐 MCP 通訊相關的錯誤
# ==========================================
class MCPError(PipelineAgentError):
    """MCP 伺服器相關的基礎錯誤"""
    pass

class MCPConnectionError(MCPError):
    """無法連接到外部 MCP 伺服器或連線中斷時觸發"""
    pass

class MCPCallError(MCPError):
    """呼叫 MCP 工具失敗 (對方回傳 isError=True) 時觸發"""
    pass