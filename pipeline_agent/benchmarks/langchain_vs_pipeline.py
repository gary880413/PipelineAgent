import asyncio
import time
import httpx
from tabulate import tabulate
from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool as lc_tool
from langchain_core.messages import HumanMessage
from langchain.agents import create_agent

from pipeline_agent import (
    tool as pa_tool,
    Runtime,
    DefaultCategory,
    PipelinePlanner,
    AsyncPipelineEngine
)

# ==========================================
# 🔧 Simulated Enterprise Scenario: Heavy I/O & Rate Limiting
# ==========================================
async def simulate_heavy_db_query(user_id: str) -> str:
    """Simulates a time-consuming internal database query (forced 3s delay)."""
    await asyncio.sleep(3.0) 
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://jsonplaceholder.typicode.com/users/{user_id}")
        data = response.json()
        return f"User {user_id}: {data['name']}, works at {data['company']['name']}."

def summarize_data(data_string: str) -> str:
    return f"--- Final Executive Report ---\n{data_string}"

# --- LangChain Tools ---
@lc_tool
def lc_fetch_user_data(user_id: str) -> str:
    """Fetch user profile data from a database. Input should be the user_id (1, 2, 3, 4)."""
    return asyncio.run(simulate_heavy_db_query(user_id))

@lc_tool
def lc_summarize(data: str) -> str:
    """Summarize fetched user data into a report. Input is the raw user data."""
    return summarize_data(data)

# --- PipelineAgent Tools ---
@pa_tool(category=DefaultCategory.DATA_ANALYSIS, runtime=Runtime.LOCAL_CPU, description="Fetch user profile data from a database. Input should be the user_id (1, 2, 3, 4).")
async def pa_fetch_user_data(user_id: str) -> str:
    return await simulate_heavy_db_query(user_id)

@pa_tool(category=DefaultCategory.TEXT_PROCESSING, runtime=Runtime.LOCAL_CPU, description="Summarize fetched user data into a report. Input is the raw user data string.")
async def pa_summarize(data: str) -> str:
    return summarize_data(data)

# Task: Fetch 4 users (testing resource locks) and summarize them.
USER_QUERY = "Please fetch the user data for user_id 1, 2, 3, and 4 using the fetch tool. Then pass all the fetched data into the summarize tool to generate a report."

# ==========================================
# 🥊 Contender 1: LangChain
# ==========================================
def run_langchain_agent() -> float:
    print("\n[LangChain] 🏃 Starting Agent (Relying on LLM's built-in tool execution)...")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    tools = [lc_fetch_user_data, lc_summarize]
    
    agent = create_agent(model=llm, tools=tools, system_prompt="You are a helpful assistant.")
    
    start_time = time.perf_counter()
    agent.invoke({"messages": [HumanMessage(content=USER_QUERY)]})
    elapsed = time.perf_counter() - start_time
    return elapsed

# ==========================================
# 🥊 Contender 2: PipelineAgent
# ==========================================
async def run_pipeline_agent() -> float:
    print("\n[PipelineAgent] 🚀 Starting DAG Engine (with strict Semaphore concurrency control)...")
    planner = PipelinePlanner()
    
    # 🌟 Core Feature: Strictly limit LOCAL_CPU to 2 concurrent tasks to protect the database
    engine = AsyncPipelineEngine(resource_limits={Runtime.LOCAL_CPU.value: 2})
    
    start_time = time.perf_counter()
    plan = planner.plan(USER_QUERY)
    result = await engine.run(plan)
    elapsed = time.perf_counter() - start_time
    
    if not result.is_success:
        print(f"PipelineAgent failed: {result.failed_tasks}")
    return elapsed

# ==========================================
# 📊 Execution & Evaluation
# ==========================================
async def main():
    print("==================================================")
    print("⚔️ Enterprise Stress Test: LangChain vs PipelineAgent ⚔️")
    print("==================================================")
    print("Test Conditions:")
    print("1. Simulated heavy database queries (3 seconds forced delay per task)")
    print("2. Concurrency limit capped at 2 (to simulate infrastructure protection)\n")

    lc_time = run_langchain_agent()
    pa_time = await run_pipeline_agent()
    
    speedup = lc_time / pa_time if pa_time > 0 else 0
    
    table = [
        ["LangChain (create_agent)", f"{lc_time:.2f}s", "Uncontrolled Concurrency / Sequential"],
        ["PipelineAgent (DAG + Lock)", f"{pa_time:.2f}s", f"{speedup:.2f}x Speedup"]
    ]
    
    print("\n📊 Benchmark Results Report:")
    print(tabulate(table, headers=["Framework", "Wall-clock Time", "Concurrency Model"], tablefmt="github"))
    print("\n💡 Architectural Analysis:")
    print("- LangChain: Execution behavior relies heavily on the LLM's parallel tool calling capabilities. Without explicit framework-level concurrency control, it may either degrade to sequential execution (slower) or fire all requests simultaneously (risking API rate limits or database overload).")
    print("- PipelineAgent: Utilizes a deterministic DAG scheduler coupled with hardware-aware resource locks. By explicitly limiting the CPU semaphore to 2, it executes tasks in controlled, predictable batches. This optimizes execution speed while actively protecting downstream infrastructure.")

if __name__ == "__main__":
    asyncio.run(main())