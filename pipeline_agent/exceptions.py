# File path: pipeline_agent/exceptions.py

class PipelineAgentError(Exception):
    """Base exception for PipelineAgent. All errors in the package should inherit from this."""
    pass

# ==========================================
# 🧠 Planner related errors
# ==========================================
class PlannerError(PipelineAgentError):
    """Error occurred during the planning stage."""
    pass

class RoutingError(PlannerError):
    """Triggered when no suitable tool class is found during the first stage routing."""
    pass

class BlueprintGenerationError(PlannerError):
    """Triggered when generating the DAG blueprint fails in the second stage (e.g., LLM returns an incorrect format)."""
    pass

# ==========================================
# ⚙️ Engine related errors
# ==========================================
class EngineError(PipelineAgentError):
    """Base error for engine execution stage."""
    pass

class DependencyResolutionError(EngineError):
    """Triggered when dependency resolution fails (e.g., output from a previous node not found)."""
    pass

class ToolExecutionError(EngineError):
    """Triggered when a single tool crashes during execution."""
    def __init__(self, task_id: str, tool_name: str, original_error: Exception):
        self.task_id = task_id
        self.tool_name = tool_name
        self.original_error = original_error
        super().__init__(f"Task '{task_id}' (Tool: {tool_name}) execution failed: {str(original_error)}")

# ==========================================
# 🌐 MCP communication related errors
# ==========================================
class MCPError(PipelineAgentError):
    """Base error for MCP server related issues."""
    pass

class MCPConnectionError(MCPError):
    """Triggered when unable to connect to the external MCP server or connection is interrupted."""
    pass

class MCPCallError(MCPError):
    """Triggered when calling an MCP tool fails (the other side returns isError=True)."""
    pass