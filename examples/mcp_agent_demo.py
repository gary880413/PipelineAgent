import os
import asyncio
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
    # Assume workspace is created in the parent directory of examples (project root)
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
        
        # 1. Web fetching MCP (developer explicitly marks as WEB_SCRAPING)
        await mcp_manager.connect_and_register(
            server_name="web_fetcher",
            command="mcp-server-fetch",
            args=[],
            override_runtime=Runtime.EXTERNAL_MCP,
            category=DefaultCategory.WEB_SCRAPING  # 🎯 Assign precise business semantics
        )

        # 2. Local filesystem MCP (developer can define a FILE_MANAGEMENT category)
        await mcp_manager.connect_and_register(
            server_name="local_fs",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", workspace_path],
            override_runtime=Runtime.EXTERNAL_MCP,
            category="FileManagement"  # 🎯 Custom categories are also fine
        )

        # ==========================================
        # 🧠 Real Task Assignment
        # ==========================================
        # Target URL: Fetch Anthropic's official MCP introduction page
        target_url = "https://modelcontextprotocol.io/introduction"
        output_file = os.path.join(workspace_path, "mcp_research_report.md")
        
        # Give explicit instructions so the planner knows which tools to use
        user_query = f"""
        Please help me complete the following automated research workflow:
        1. Use the fetch tool to retrieve the content of this URL: {target_url}
        2. Pass the fetched content to the generate_markdown_report tool for summarization and translation.
        3. Use the write_file tool to save the generated Markdown report to this path: {output_file}
        """
        
        print(f"\n🧠 The planner is starting to plan the task...")
        current_plan = planner.plan(user_query)

        # ==========================================
        # ⚙️ Engine Scheduling and Agentic Loop (Self-healing Loop)
        # ==========================================
        max_retries = 3
        attempt = 1
        is_success = False
        
        while attempt <= max_retries:
            print(f"\n=============================================")
            print(f"⚙️ Engine execution (Round {attempt}/{max_retries})")
            print(f"=============================================")
            
            is_success, state, failed = await engine.run(current_plan)

            if is_success:
                print(f"\n🎉 Task completed successfully! Please check your folder: {output_file}")
                if os.path.exists(output_file):
                    print("\n📄 Preview of the generated file content:")
                    print("-" * 50)
                    with open(output_file, 'r', encoding='utf-8') as f:
                        print(f.read())
                    print("-" * 50)
                break  # Exit loop on success
            else:
                print(f"\n⚠️ Execution failed! Failed node: {failed}")
                if attempt < max_retries:
                    print("\n🚨 Initiating dynamic re-planning...")
                    # Show the planner the reason for failure (including unexpected keyword argument 'content')
                    current_plan = planner.replan(
                        original_goal=user_query,
                        current_state=state,
                        failed_nodes=failed
                    )
                attempt += 1

        if not is_success:
            print("\n❌ Retry limit reached, task ultimately failed.")

    finally:
        print("\n🧹 Cleaning up system resources...")
        await mcp_manager.close_all()
        print("👋 System shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())