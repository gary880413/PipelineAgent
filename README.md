# 🚀 PipelineAgent

**PipelineAgent** is an asynchronous AI Agent framework purpose-built for **Cloud-Edge Collaboration**.

It breaks away from the slow, blocking "single-step loop" of traditional Agents (like ReAct) and transforms the Large Language Model (LLM) into a **"Macro-Pipeline Architect"**. By dynamically generating Directed Acyclic Graphs (DAGs) and offloading execution to a hardware-aware local engine asynchronously, it maximizes every drop of compute power from your CPU and GPU.

## ✨ Core Features

1. **Decoupling Control & Execution:** The Cloud Brain (Planner) is strictly responsible for logical orchestration and DAG blueprint generation. The Edge Engine handles dependency resolution, variable injection (supporting string interpolation), and asynchronous scheduling.
2. **Hardware-Aware Routing:** Developers can tag tools with a specific `Runtime` (e.g., `LOCAL_CPU`, `LOCAL_GPU`, `CLOUD_API`). The underlying engine uses `Semaphore` locks to strictly control concurrency, perfectly protecting local VRAM from OOM (Out of Memory) crashes.
3. **Seamless Global Ecosystem (MCP Support):** Native support for the Model Context Protocol (MCP). With just two lines of code, external servers (Node.js or Python, e.g., GitHub, Filesystem, Web Fetchers) can be mounted as local tools and assigned independent resource locks.
4. **Dynamic Self-Healing (Agentic Loop):** When a local tool encounters an irreversible error (e.g., GPU crash, API denial, parameter type mismatch), the engine gracefully interrupts and sends a "disaster log" back to the cloud. The brain dynamically generates a "remedial DAG" based on the remaining tasks to seamlessly resume the workflow.

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

## 🗺️ Roadmap

- [x] MCP (Model Context Protocol) Integration: Support standard MCP for plug-and-play tools and resource management.
- [ ] Semantic Tool Retrieval: Transition from string-matching routing to Vector DB-based RAG retrieval. This ensures the brain can accurately fetch required tools even when hundreds of MCP tools are mounted, avoiding Context Window overflow.
- [ ] Artifacts Store: Solve the "memory bomb" issue caused by passing large binary files (like videos or massive DataFrames) between nodes. Transition global memory to pass Pointers/URIs, writing actual files to disk or S3.
- [ ] Human-in-the-Loop (HITL): Implement Approval Nodes. Pause the execution thread when the pipeline reaches sensitive operations, waiting for an external human authorization signal.

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the issues page or submit a Pull Request.