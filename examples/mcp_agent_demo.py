import os
import asyncio
from dotenv import load_dotenv
from openai import AsyncOpenAI

# 載入環境變數 (確保有 OPENAI_API_KEY)
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
# 🔧 真實的本地工具：AI 報告排版引擎
# ==========================================
@tool(
    category=DefaultCategory.TEXT_PROCESSING,
    runtime=Runtime.CLOUD_API, 
    description="將原始網頁內容翻譯成繁體中文，並整理成結構化的 Markdown 報告。需要傳入 raw_text 參數。"
)
async def generate_markdown_report(raw_text: str) -> str:
    print("   [本地工具] 正在呼叫 OpenAI 將原始文本轉換為精美報告...")
    client = AsyncOpenAI()
    
    # 避免網頁內容過長塞爆 Token，我們擷取前 2000 個字元
    truncated_text = raw_text[:2000] 
    
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "你是一個專業的技術編輯。請將以下網頁內容總結出 3 個核心重點，並翻譯成流暢的繁體中文，最後以 Markdown 格式輸出。"},
            {"role": "user", "content": truncated_text}
        ],
        temperature=0.3
    )
    return response.choices[0].message.content


# ==========================================
# 🚀 系統啟動與 Agentic Loop
# ==========================================
async def main():
    print("🚀 啟動 PipelineAgent (真實環境整合模式)...")

    # 取得 workspace 的絕對路徑 (Filesystem MCP 的安全要求)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 假設 workspace 建立在 examples 的上一層 (專案根目錄)
    workspace_path = os.path.abspath(os.path.join(current_dir, "..", "workspace"))
    
    # 確保資料夾存在
    os.makedirs(workspace_path, exist_ok=True)
    print(f"📂 授權的本地寫入目錄: {workspace_path}")

    mcp_manager = MCPClientManager()
    planner = PipelinePlanner()
    engine = AsyncPipelineEngine(resource_limits={
        Runtime.LOCAL_CPU.value: 10,
        Runtime.CLOUD_API.value: 10,
        Runtime.EXTERNAL_MCP.value: 5
    })

    try:
        # ==========================================
        # 🌐 掛載雙重 MCP 伺服器
        # ==========================================
        print("\n🔌 正在掛載外部 MCP 伺服器...")
        
        # 1. 抓取網頁的 MCP (開發者明確標記為 WEB_SCRAPING)
        await mcp_manager.connect_and_register(
            server_name="web_fetcher",
            command="mcp-server-fetch",
            args=[],
            override_runtime=Runtime.EXTERNAL_MCP,
            category=DefaultCategory.WEB_SCRAPING  # 🎯 精準賦予業務語義
        )

        # 2. 本地檔案系統的 MCP (開發者可以自定義一個 FILE_MANAGEMENT 類別)
        await mcp_manager.connect_and_register(
            server_name="local_fs",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", workspace_path],
            override_runtime=Runtime.EXTERNAL_MCP,
            category="FileManagement"  # 🎯 自定義分類也完全沒問題
        )

        # ==========================================
        # 🧠 真實任務指派
        # ==========================================
        # 目標網址：我們去抓 Anthropic 關於 MCP 的官方介紹網頁
        target_url = "https://modelcontextprotocol.io/introduction"
        output_file = os.path.join(workspace_path, "mcp_research_report.md")
        
        # 刻意給出明確的指示，讓大腦知道要串接哪些工具
        user_query = f"""
        請幫我完成以下自動化研究流程：
        1. 使用 fetch 工具去抓取這個網址的內容：{target_url}
        2. 將抓到的內容交給 generate_markdown_report 工具進行總結與翻譯。
        3. 使用 write_file 工具，將生成的 Markdown 報告儲存到此路徑：{output_file}
        """
        
        print(f"\n🧠 大腦開始規劃任務...")
        current_plan = planner.plan(user_query)

        # ==========================================
        # ⚙️ 引擎排程與 Agentic Loop (自我修復迴圈)
        # ==========================================
        max_retries = 3
        attempt = 1
        is_success = False
        
        while attempt <= max_retries:
            print(f"\n=============================================")
            print(f"⚙️ 引擎開始執行 (回合 {attempt}/{max_retries})")
            print(f"=============================================")
            
            is_success, state, failed = await engine.run(current_plan)

            if is_success:
                print(f"\n🎉 任務大功告成！請去檢查你的資料夾：{output_file}")
                if os.path.exists(output_file):
                    print("\n📄 產出的檔案內容預覽：")
                    print("-" * 50)
                    with open(output_file, 'r', encoding='utf-8') as f:
                        print(f.read())
                    print("-" * 50)
                break  # 成功就跳出迴圈
            else:
                print(f"\n⚠️ 執行失敗！失敗節點: {failed}")
                if attempt < max_retries:
                    print("\n🚨 啟動動態重規劃 (Re-planning)...")
                    # 讓大腦看到失敗原因 (包含 unexpected keyword argument 'content')
                    current_plan = planner.replan(
                        original_goal=user_query,
                        current_state=state,
                        failed_nodes=failed
                    )
                attempt += 1

        if not is_success:
            print("\n❌ 耗盡重試次數，任務最終失敗。")

    finally:
        print("\n🧹 正在清理系統資源...")
        await mcp_manager.close_all()
        print("👋 系統關閉完成。")

if __name__ == "__main__":
    asyncio.run(main())