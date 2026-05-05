import asyncio

from dotenv import load_dotenv # 🌟 Import dotenv

# 🌟 Load environment variables before importing any other packages
load_dotenv()

from pipeline_agent import (
    tool, 
    Runtime, 
    DefaultCategory, 
    PipelinePlanner, 
    AsyncPipelineEngine
)

# --- 1. Tool Definitions and Resource Declarations ---

@tool(
    category=DefaultCategory.WEB_SCRAPING, 
    runtime=Runtime.LOCAL_CPU, 
    description="Fetch webpage source code."
)
async def fetch_webpage(url: str) -> str:
    print(f"   [CPU] Fetching {url} ...")
    await asyncio.sleep(1)
    return f"<html>{url} long source code...with lots of noise...</html>"

# 🚨 Intentionally design a local GPU tool that will crash
@tool(
    category=DefaultCategory.TEXT_PROCESSING, 
    runtime=Runtime.LOCAL_GPU, 
    description="Use local GPU to quickly filter text noise and extract key points. Preferred tool."
)
async def local_gpu_summarizer(text: str) -> str:
    print(f"   [GPU] Preparing to send text to local model...")
    await asyncio.sleep(1)
    raise RuntimeError("CUDA Out of Memory: Local GPU VRAM insufficient, inference failed.")

# ☁️ Cloud backup tool
@tool(
    category=DefaultCategory.TEXT_PROCESSING, 
    runtime=Runtime.CLOUD_API, 
    description="Use cloud API to filter text noise and extract key points. Backup tool when GPU is unavailable."
)
async def cloud_api_summarizer(text: str) -> str:
    print(f"   [Cloud] Received backup request, calling remote model...")
    await asyncio.sleep(2)
    return "Successfully summarized via cloud API: 1. Resource scheduling is important. 2. Fault tolerance is key."

@tool(
    category=DefaultCategory.DATA_ANALYSIS, 
    runtime=Runtime.CLOUD_API, 
    description="Write analysis report based on key points."
)
async def write_report(points: str) -> str:
    print(f"   [Cloud] Writing final analysis report...")
    await asyncio.sleep(1)
    return f"Final report: Based on intelligence ({points}), our architecture is very robust."


# --- 2. System Startup and Agentic Loop ---
async def main():
    user_query = "Fetch the webpage of example.com, filter out the noise and summarize the key points, then write an analysis report."
    
    # 1. Initialize Planner
    planner = PipelinePlanner() 
    
    # 2. Dynamically configure resource limits based on current hardware
    custom_limits = {
        Runtime.LOCAL_CPU.value: 20, 
        Runtime.LOCAL_GPU.value: 1,  # Strictly protect single GPU
        Runtime.CLOUD_API.value: 10
    }
    engine = AsyncPipelineEngine(resource_limits=custom_limits) 
    
    # 3. Initial planning
    current_plan = await planner.plan(user_query)
    
    # 4. Agentic Loop (Dynamic Fault Tolerance and Replanning Mechanism)
    max_retries = 3
    attempt = 1
    
    # 宣告在迴圈外以利最後印出狀態
    final_result = None
    
    while attempt <= max_retries:
        print(f"\n=============================================")
        print(f"  Execution round {attempt}/{max_retries}")
        print(f"=============================================")
        
        # 🚨 修正：統一使用 EngineResult 物件接收
        final_result = await engine.run(current_plan)
        
        if final_result.is_success:
            print("\n🎉 Task completed successfully!")
            break
        else:
            print(f"\n⚠️ Encountered a setback, Agent triggers dynamic replanning (preparing for round {attempt+1})...")
            # 🌟 修正：正確傳遞 final_state 與 failed_tasks 給 Planner
            current_plan = await planner.replan(
                original_goal=user_query,
                current_state=final_result.final_state,
                failed_nodes=final_result.failed_tasks
            )
            attempt += 1

    # 5. Output final result
    if final_result and not final_result.is_success:
        print("\n💀 Retry limit reached, Agent gives up the task.")
        
    print("\n[Final global state (memory)]: ")
    if final_result:
        for k, v in final_result.final_state.items():
            if not isinstance(v, Exception):
                print(f"{k}: {str(v)[:80]}...")

if __name__ == "__main__":
    asyncio.run(main())