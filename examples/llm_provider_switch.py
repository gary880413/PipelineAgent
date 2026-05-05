"""
LLM Provider Switch Demo
=========================
Demonstrates how PipelineAgent can run the same workflow across different LLM backends
by simply switching PipelineConfig — no code changes required in tools or engine.

Supported providers:
  - openai           (default, uses OPENAI_API_KEY env var)
  - ollama           (local, auto-points to http://localhost:11434/v1)
  - azure            (Azure OpenAI Service, needs endpoint + api_version)
  - openai_compatible (any OpenAI-compatible API, specify base_url)
"""

import asyncio
from dotenv import load_dotenv

load_dotenv()

from pipeline_agent import (
    tool,
    Runtime,
    DefaultCategory,
    PipelinePlanner,
    AsyncPipelineEngine,
)
from pipeline_agent.config import PipelineConfig


# ==========================================
# 🔧 Define a simple tool for demonstration
# ==========================================
@tool(
    category=DefaultCategory.TEXT_PROCESSING,
    runtime=Runtime.LOCAL_CPU,
    description="Summarize the given text into one sentence.",
    timeout=30  # Tool-level timeout override (30 seconds)
)
async def summarize(text: str) -> str:
    return f"Summary: {text[:80]}..."


@tool(
    category=DefaultCategory.TEXT_PROCESSING,
    runtime=Runtime.LOCAL_CPU,
    description="Translate text to Traditional Chinese.",
)
async def translate_to_zh(text: str) -> str:
    return f"[翻譯結果] {text}"


# ==========================================
# 🧪 Provider Configs
# ==========================================

def get_openai_config() -> PipelineConfig:
    """Standard OpenAI (reads OPENAI_API_KEY from env)"""
    return PipelineConfig(
        llm_provider="openai",
        model_name="gpt-4o-mini",
    )


def get_ollama_config() -> PipelineConfig:
    """Local Ollama (must have `ollama serve` running with a model pulled)"""
    return PipelineConfig(
        llm_provider="ollama",
        model_name="qwen2.5:7b",  # Change to whichever model you have pulled
        # llm_base_url auto-defaults to http://localhost:11434/v1
    )


def get_azure_config() -> PipelineConfig:
    """Azure OpenAI (set your endpoint and key)"""
    return PipelineConfig(
        llm_provider="azure",
        model_name="gpt-4o-mini",  # This is the deployment name in Azure
        azure_endpoint="https://your-resource.openai.azure.com/",
        azure_api_version="2024-08-01-preview",
        # llm_api_key="your-azure-key",  # Or set AZURE_OPENAI_API_KEY env var
    )


def get_compatible_config() -> PipelineConfig:
    """Any OpenAI-compatible endpoint (vLLM, LiteLLM, Together AI, etc.)"""
    return PipelineConfig(
        llm_provider="openai_compatible",
        model_name="meta-llama/Llama-3-8b-chat-hf",
        llm_base_url="http://localhost:8000/v1",
        llm_api_key="token-placeholder",
    )


def get_anthropic_config() -> PipelineConfig:
    """Anthropic Claude (requires `pip install pipeline-agent[anthropic]`)
    Anthropic Claude（需安裝 anthropic 額外依賴）"""
    return PipelineConfig(
        llm_provider="anthropic",
        model_name="claude-sonnet-4-5",
        # llm_api_key="...",  # Or set ANTHROPIC_API_KEY env var
    )


# ==========================================
# 🚀 Main
# ==========================================

async def run_with_provider(config: PipelineConfig):
    print(f"\n{'='*60}")
    print(f"🧠 Provider: {config.llm_provider} | Model: {config.model_name}")
    if config.llm_base_url:
        print(f"   Base URL: {config.llm_base_url}")
    print(f"{'='*60}")

    planner = PipelinePlanner(config=config)
    engine = AsyncPipelineEngine(config=config)

    user_query = "Summarize the text 'PipelineAgent is a DAG-based async AI framework' then translate the result to Chinese."

    try:
        plan = await planner.plan(user_query)
        print(f"✅ DAG generated: {len(plan.nodes)} nodes")
        for node in plan.nodes:
            print(f"   - {node.task_id}: {node.tool_name} (depends_on={node.depends_on})")

        result = await engine.run(plan)

        if result.is_success:
            print(f"🎉 Success! Final outputs:")
            for task_id, output in result.final_state.items():
                print(f"   [{task_id}] → {str(output)[:100]}")
        else:
            print(f"❌ Failed: {result.failed_tasks}")

    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")


async def main():
    # ===== Switch the config here to test different providers =====
    # Uncomment the provider you want to test:

    config = get_openai_config()
    # config = get_ollama_config()
    # config = get_azure_config()
    # config = get_compatible_config()
    # config = get_anthropic_config()

    await run_with_provider(config)


if __name__ == "__main__":
    asyncio.run(main())
