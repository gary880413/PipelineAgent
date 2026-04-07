import os
import asyncio
import sys
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load environment variables (make sure OPENAI_API_KEY is set)
load_dotenv()

from pipeline_agent import (
    tool,
    Runtime,
    DefaultCategory,
    PipelinePlanner,
    AsyncPipelineEngine,
    MCPClientManager
)

# ==========================================
# 🔧 Real Local Tool: AI Report Formatting Engine
# ==========================================
@tool(
    category=DefaultCategory.TEXT_PROCESSING,
    runtime=Runtime.CLOUD_API, 
    description="Translate raw web page content into Traditional Chinese and organize it into a structured Markdown report. Requires the raw_text parameter."
)
async def generate_markdown_report(raw_text: str) -> str:
    print("   [Local Tool] Calling OpenAI to convert raw text into a polished report...")
    client = AsyncOpenAI()
    
    # To avoid exceeding token limits, truncate to the first 2000 characters
    truncated_text = raw_text[:2000] 
    
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a professional technical editor. Please summarize the following web content into 3 key points, translate it into fluent Traditional Chinese, and output in Markdown format."},
            {"role": "user", "content": truncated_text}
        ],
        temperature=0.3
    )
    return response.choices[0].message.content


# ==========================================
# 🚀 System Startup and Agentic Loop
# ==========================================
async def main():
    print("🚀 Starting PipelineAgent (Real Environment Integration Mode)...")

    # Get the absolute path of the workspace (required for Filesystem MCP security)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_path = os.path.abspath(os.path.join(current_dir, "..", "workspace"))
    
    # Ensure the folder exists
    os.makedirs(workspace_path, exist_ok=True)
    print(f"📂 Authorized local write directory: {workspace_path}")

    mcp_manager = MCPClientManager()
    planner = PipelinePlanner()
    engine = AsyncPipelineEngine(resource_limits={
        Runtime.LOCAL_CPU.value: 10,
        Runtime.CLOUD_API.value: 10,
        Runtime.EXTERNAL_MCP.value: 5
    })

    try:
        # ==========================================
        # 🌐 Mount Dual MCP Servers
        # ==========================================
        print("\n🔌 Mounting external MCP servers...")
        
        # 1. Web fetching MCP
        await mcp_manager.connect_and_register(
            server_name="web_fetcher",
            command=sys.executable,
            args=["-m", "mcp_server_fetch"],  # 🌟 注意：Python 呼叫 module 時名稱是用底線 (mcp_server_fetch)
            override_runtime=Runtime.EXTERNAL_MCP,
            category=DefaultCategory.WEB_SCRAPING  
        )
        # 2. Local filesystem MCP
        await mcp_manager.connect_and_register(
            server_name="local_fs",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", workspace_path],
            override_runtime=Runtime.EXTERNAL_MCP,
            category="FileManagement"  
        )

        # ==========================================
        # 🧠 Real Task Assignment
        # ==========================================
        target_url = "https://modelcontextprotocol.io/introduction"
        output_file = os.path.join(workspace_path, "mcp_research_report.md")
        
        user_query = f"""
        Please help me complete the following automated research workflow:
        1. Use the fetch tool to retrieve the content of this URL: {target_url}
        2. Pass the fetched content to the generate_markdown_report tool for summarization and translation.
        3. Use the write_file tool to save the generated Markdown report to this path: {output_file}
        """
        
        print(f"\n🧠 The planner is starting to plan the task...")
        current_plan = planner.plan(user_query)

        # ==========================================
        # ⚙️ Engine Scheduling and Agentic Loop
        # ==========================================
        max_retries = 3
        attempt = 1
        
        while attempt <= max_retries:
            print(f"\n=============================================")
            print(f"⚙️ Engine execution (Round {attempt}/{max_retries})")
            print(f"=============================================")
            
            # 🚨 修正：使用 EngineResult 物件接收回傳值
            result = await engine.run(current_plan)

            if result.is_success:
                print(f"\n🎉 Task completed successfully! Please check your folder: {output_file}")
                if os.path.exists(output_file):
                    print("\n📄 Preview of the generated file content:")
                    print("-" * 50)
                    with open(output_file, 'r', encoding='utf-8') as f:
                        print(f.read())
                    print("-" * 50)
                break  # Exit loop on success
            else:
                print(f"\n⚠️ Execution failed! Failed nodes: {result.failed_tasks}")
                
                if attempt < max_retries:
                    print("\n🚨 Initiating dynamic re-planning (Self-Healing)...")
                    # 💡 提示：此處依賴底層的 CheckpointManager 來防止已成功節點被重複執行
                    # 🚨 修正：傳入正確的狀態與錯誤物件
                    current_plan = planner.replan(
                        original_goal=user_query,
                        current_state=result.final_state,
                        failed_nodes=result.failed_tasks
                    )
                attempt += 1

        if attempt > max_retries: # Loop finished without breaking
            print("\n❌ Retry limit reached, task ultimately failed.")

    finally:
        print("\n🧹 Cleaning up system resources...")
        await mcp_manager.close_all()
        print("👋 System shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())