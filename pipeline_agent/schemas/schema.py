from enum import Enum
from typing import List, Dict, Any
from pydantic import BaseModel, Field

# ==========================================
# 🏷️ 基礎定義 (Enums)
# ==========================================

class Runtime(str, Enum):
    """
    定義任務執行的資源環境，引擎將根據此標記分配 Semaphore 鎖。
    """
    LOCAL_CPU = "local_cpu"
    LOCAL_GPU = "local_gpu"
    CLOUD_API = "cloud_api"
    EXTERNAL_MCP = "external_mcp"  # 🌟 專供外部 MCP Server 使用

# ==========================================
# 🏗️ 核心數據模型 (Models for LLM Generation)
# ==========================================
# ⚠️ 注意：這些模型會被傳給 OpenAI 的 Structured Outputs，
# 因此型別必須保持簡單清晰，避免使用過度複雜的 Union。

class TaskNode(BaseModel):
    """
    DAG 中的單一任務節點。
    """
    task_id: str = Field(..., description="唯一的任務標識符，如 'fetch_web_01'")
    tool_name: str = Field(..., description="要調用的工具名稱")
    runtime: str = Field(..., description="該任務所需的運行資源類型，例如 'local_cpu', 'external_mcp'")
    tool_inputs_json: str = Field(
        ..., 
        description="工具的輸入參數 (必須是 JSON 格式的字串)。支援 ${task_id.output} 語法來引用前置任務的結果"
    )
    depends_on: List[str] = Field(
        default_factory=list, 
        description="此節點所依賴的前置 task_id 列表"
    )

class DAGPlan(BaseModel):
    """
    大腦生成的完整執行計畫藍圖。
    """
    plan_id: str = Field(..., description="計畫的唯一追蹤 ID")
    goal: str = Field(..., description="原始任務目標描述")
    nodes: List[TaskNode] = Field(..., description="所有任務節點的清單")


# ==========================================
# ⚙️ 執行結果模型 (Execution Results for Developers)
# ==========================================

class EngineResult(BaseModel):
    """
    引擎執行完畢後回傳給開發者的標準化結果物件。
    用來取代原本難以閱讀的 Tuple 回傳值。
    """
    is_success: bool = Field(..., description="流程是否完整無誤地執行成功")
    final_state: Dict[str, Any] = Field(
        default_factory=dict, 
        description="所有成功節點的輸出結果庫 {task_id: output}"
    )
    failed_tasks: Dict[str, str] = Field(
        default_factory=dict,
        description="失敗節點的錯誤訊息 {task_id: error_message}"
    )