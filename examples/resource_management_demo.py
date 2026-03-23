import asyncio
import time
from dotenv import load_dotenv

load_dotenv()

from pipeline_agent import (
    tool,
    Runtime,
    DefaultCategory,
    PipelinePlanner,
    AsyncPipelineEngine
)

# ==========================================
# 🔧 Define tools (simulate different resource-consuming characteristics)
# ==========================================

@tool(
    category=DefaultCategory.WEB_SCRAPING,
    runtime=Runtime.LOCAL_CPU, 
    description="Fetch the latest market news and financial summary for a given company. I/O intensive task."
)
async def fetch_market_news(company_symbol: str) -> str:
    print(f"   [CPU NIC] 🌐 Start fetching data for {company_symbol} in parallel...")
    await asyncio.sleep(1) # Simulate network I/O latency
    print(f"   [CPU NIC] ✅ Data download completed for {company_symbol}!")
    return f"[{company_symbol} Raw financial data: Revenue growth, strong market response]"


@tool(
    category=DefaultCategory.TEXT_PROCESSING,
    runtime=Runtime.LOCAL_GPU, 
    description="Run open-source LLM on local GPU to perform deep sentiment analysis on financial reports. Computation intensive and highly VRAM-consuming."
)
async def analyze_sentiment_gpu(news_content: str) -> str:
    print(f"   [GPU Core] 🔥 Loading data into VRAM for inference: {news_content[:10]}...")
    await asyncio.sleep(3) # Simulate long inference time on local GPU
    print(f"   [GPU Core] 🧊 Inference completed, VRAM released.")
    return f"Sentiment analysis result: Highly optimistic ({news_content[:10]})"


@tool(
    category=DefaultCategory.DATA_ANALYSIS,
    runtime=Runtime.CLOUD_API, 
    description="Aggregate multiple sentiment analysis reports and use cloud computing power to generate the final investment strategy. Requires a string containing all analysis results."
)
async def generate_investment_strategy(all_analyses: str) -> str:
    print(f"   [Cloud API] ☁️ Calling remote large model to generate final strategy...")
    await asyncio.sleep(2)
    return "[Final investment portfolio strategy]: Overweight AI infrastructure, hold leading foundries."


# ==========================================
# 🚀 System startup and Agentic Loop
# ==========================================
async def main():
    print("🚀 Starting PipelineAgent (Resource Stress Test Mode)...")

    planner = PipelinePlanner()
    
    # 🌟 Key point: Strict resource control lock (Semaphore)
    engine = AsyncPipelineEngine(resource_limits={
        Runtime.LOCAL_CPU.value: 10,  # Allow 10 threads to fetch web pages concurrently
        Runtime.LOCAL_GPU.value: 1,   # ⚠️ Strictly protect VRAM! Only 1 local inference at a time
        Runtime.CLOUD_API.value: 5
    })

    # Explicitly instruct the LLM to fan-out, forcing it to draw a parallel DAG
    user_query = """
    Please fetch and deeply analyze the latest market news and financial sentiment for these five tech giants: NVDA, TSMC, AAPL, MSFT, GOOGL.
    Finally, based on the sentiment analysis results of these five companies, please aggregate and generate a final investment strategy report.
    """
    
    print("\n🧠 Brain starts planning large-scale DAG blueprint...")
    plan = planner.plan(user_query)
    
    print("\n📋 Generated DAG blueprint (check for fan-out and fan-in):")
    # Printing the blueprint here allows you to verify if the LLM really created a parallel structure
    print(plan.model_dump_json(indent=2))

    print("\n=============================================")
    print("⚙️ Engine starts asynchronous scheduling execution (observe the timing in the terminal output)")
    print("=============================================")
    
    start_time = time.time()
    
    # 🚨 修正：使用 EngineResult 物件接收
    engine_result = await engine.run(plan)
    
    elapsed_time = time.time() - start_time

    if engine_result.is_success:
        print(f"\n🎉 Task completed successfully! Total elapsed time: {elapsed_time:.2f} seconds")
        # If executed sequentially (ReAct mode), time would be (1+3)*5 + 2 = 22 seconds
        # In our Pipeline, fetch (1s parallel) + GPU inference (3s, queued 5 times = 15s) + aggregation (2s) = theoretical time about 18 seconds
        
        # 🚨 修正：從 final_state 取出結果 (避免變數名稱遮蔽，改為 task_output)
        for task_id, task_output in engine_result.final_state.items():
            if "strategy" in task_id.lower() or "generate" in task_id.lower():
                print(f"\n📄 Final output: {task_output}")
    else:
        # 🚨 修正：印出 failed_tasks
        print(f"\n❌ Execution failed, failed nodes: {engine_result.failed_tasks}")

if __name__ == "__main__":
    asyncio.run(main())