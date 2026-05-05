from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, Optional

class PipelineConfig(BaseSettings):
    """
    Global configuration center for PipelineAgent.
    Supports loading from: code defaults → .env file → environment variables (PIPELINE_ prefix).
    
    PipelineAgent 的全局配置中心。
    支援從以下來源載入：程式碼預設值 → .env 檔 → 環境變數（PIPELINE_ 前綴）。
    
    Example environment variables:
        PIPELINE_LLM_PROVIDER=ollama
        PIPELINE_MODEL_NAME=qwen2.5:7b
        PIPELINE_NODE_TIMEOUT_SEC=60
        PIPELINE_ENABLE_TRACING=false
    """
    
    model_config = SettingsConfigDict(
        env_prefix="PIPELINE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # ==========================================
    # 🧠 Planner & LLM Settings (大腦與規劃層設定)
    # ==========================================
    
    # The LLM provider to use (e.g., 'openai', 'anthropic', 'ollama')
    # 使用的 LLM 供應商 (例如：'openai', 'anthropic', 'ollama')
    llm_provider: str = Field(default="openai")
    
    # The specific model name for the planner
    # 規劃者使用的具體模型名稱
    model_name: str = Field(default="gpt-4o-mini")
    
    # Custom base URL for OpenAI-compatible endpoints (Ollama, vLLM, LiteLLM proxy, etc.)
    # 自訂的 OpenAI 相容端點 URL（Ollama、vLLM、LiteLLM proxy 等）
    llm_base_url: Optional[str] = Field(default=None)
    
    # Explicit API key override (if not set, falls back to env vars)
    # 明確指定 API Key（若未設，退回環境變數）
    llm_api_key: Optional[str] = Field(default=None)
    
    # Azure OpenAI specific: API version string
    # Azure OpenAI 專用：API 版本字串
    azure_api_version: Optional[str] = Field(default=None)
    
    # Azure OpenAI specific: deployment endpoint (e.g., https://myresource.openai.azure.com/)
    # Azure OpenAI 專用：部署端點
    azure_endpoint: Optional[str] = Field(default=None)

    # The core system prompt instructing the LLM how to behave
    # 指導 LLM 如何行為的核心系統提示詞
    system_prompt: str = Field(
        default="You are an expert AI planner. Your task is to break down the user's goal into a logical Directed Acyclic Graph (DAG) of tool calls.",
    )

    # ==========================================
    # 📂 Storage & Observability (儲存與觀測層設定)
    # ==========================================
    
    # Base directory for storing checkpoints, traces, and workspace files
    # 儲存快照、軌跡與工作區檔案的根目錄
    workspace_dir: str = Field(default=".pipeline_workspace")
    
    # Toggle to enable/disable writing execution traces to disk
    # 啟用/停用將執行軌跡寫入硬碟的開關
    enable_tracing: bool = Field(default=True)
    
    # Toggle to enable/disable state checkpointing (Exactly-Once semantics)
    # 啟用/停用狀態快照的開關 (Exactly-Once 語意保證)
    enable_checkpointing: bool = Field(default=True)

    # ==========================================
    # ⚙️ Execution Engine Settings (執行引擎層設定)
    # ==========================================
    
    # Maximum execution time allowed for a single node (in seconds)
    # 單一節點允許的最大執行時間 (秒數)
    node_timeout_sec: int = Field(default=120)
    
    # Default concurrency limits for different resource pools
    # 不同資源池的預設併發限制
    default_resource_limits: Dict[str, int] = Field(
        default_factory=lambda: {
            "local_cpu": 10,
            "local_gpu": 1,
            "cloud_api": 5,
            "external_mcp": 5
        }
    )