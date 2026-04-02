# 🚀 PipelineAgent

**PipelineAgent** is an asynchronous AI Agent framework purpose-built for **Cloud-Edge Collaboration**.

It shifts away from the sequential "single-step loop" of traditional Agents (like ReAct) and transforms the LLM into a "Macro-Pipeline Architect". By generating Directed Acyclic Graphs (DAGs) upfront and offloading execution to a hardware-aware local engine, it enables parallel task execution and explicit concurrency control.

## ✨ Core Features

1. **Decoupling Control & Execution:** The Cloud Brain (Planner) is strictly responsible for logical orchestration and DAG blueprint generation. The Edge Engine handles dependency resolution, variable injection (supporting string interpolation), and asynchronous scheduling.
2. **Hardware-Aware Routing:** Developers can tag tools with a specific Runtime (e.g., LOCAL_CPU, LOCAL_GPU, CLOUD_API). The underlying engine utilizes explicit Semaphore locking per runtime tag to strictly constrain concurrency, mitigating the risk of OOM crashes during heavy parallel loads.
3. **Seamless Global Ecosystem (MCP Support):** Native support for the Model Context Protocol (MCP). With just two lines of code, external servers (Node.js or Python, e.g., GitHub, Filesystem, Web Fetchers) can be mounted as local tools and assigned independent resource locks.
4. **Dynamic Self-Healing (Agentic Loop) (Experimental):** When a local tool encounters an irreversible error, the engine halts the execution and generates a "disaster log". We are actively experimenting with dynamic "remedial DAG" generation to allow the brain to recover and resume workflows.

## 📊 Project Status & Roadmap

To maintain transparency regarding the framework's maturity, here is the current implementation status:

| Feature Area | Status | Description |
| :--- | :---: | :--- |
| **DAG Generation** | 🟢 Implemented | LLM accurately translates user intents into dependency-mapped JSON structures. |
| **Async Execution Engine** | 🟢 Implemented | `asyncio`-based event loop with topological sorting and variable injection (`${node.output}`). |
| **Resource Isolation** | 🟢 Implemented | Hard concurrency limits via `Semaphore` per runtime (CPU, GPU, MCP). |
| **MCP Integration** | 🟢 Implemented | Dynamic mounting and lifecycle management of standard MCP tools. |
| **Error Halting** | 🟢 Implemented | Safe termination of dependent subgraphs upon upstream node failure. |
| **Agentic Self-Healing** | 🟡 Experimental | Generation of disaster logs and prompting for remedial DAGs (Proof-of-Concept stage). |
| **Semantic Tool Retrieval** | ⚪ Planned | Replacing brute-force tool context injection with Vector DB / RAG retrieval. |
| **State/Memory Persistence**| ⚪ Planned | Transitioning from in-memory DAG state to persistent artifact stores. |

*(🟢 Implemented / 🟡 Experimental / ⚪ Planned)*

## 📦 Installation

The project currently supports developer mode installation:

```bash
git clone https://github.com/GaryChang/PipelineAgent.git
cd PipelineAgent

# After creating and activating your virtual environment:
pip install -e .
# (Please ensure you have a .env file ready with your OPENAI_API_KEY configured)
```

## 🛠️ Quick Start

PipelineAgent provides extremely clean APIs, allowing you to easily mix local custom tools with external MCP servers.

```python
import asyncio
from pipeline_agent import (
    tool, Runtime, DefaultCategory, 
    PipelinePlanner, AsyncPipelineEngine, MCPClientManager
)

# 1. Define a local GPU task (protected by strict concurrency constraints)
@tool(category=DefaultCategory.TEXT_PROCESSING, runtime=Runtime.LOCAL_GPU, description="Analyze data using a local model")
async def analyze_local(text: str) -> str:
    return f"Analysis complete: {text}"

async def main():
    mcp_manager = MCPClientManager()
    planner = PipelinePlanner() 
    
    # Define hardware resource limits (Strictly lock GPU to 1 concurrent task)
    engine = AsyncPipelineEngine(resource_limits={
        Runtime.LOCAL_CPU.value: 10,
        Runtime.LOCAL_GPU.value: 1,
        Runtime.EXTERNAL_MCP.value: 5
    }) 
    
    try:
        # 2. Mount an external MCP server (e.g., the official fetch tool)
        await mcp_manager.connect_and_register(
            server_name="web_fetcher",
            command="mcp-server-fetch",
            args=[],
            override_runtime=Runtime.EXTERNAL_MCP,
            category=DefaultCategory.WEB_SCRAPING
        )

        # 3. Brain Planning & Engine Execution
        user_query = "Fetch the webpage from example.com and analyze it using the local model."
        plan = planner.plan(user_query)
        result = await engine.run(plan)
    
        if result.is_success:
            print("Final state:", result.final_state)
        else:
            print("Failed tasks:", result.failed_tasks)
        
    finally:
        # Gracefully shutdown external subprocesses
        await mcp_manager.close_all()

if __name__ == "__main__":
    asyncio.run(main())
```

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the issues page or submit a Pull Request.