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
# 🔧 定義工具 (刻意模擬不同資源的耗時特性)
# ==========================================

@tool(
    category=DefaultCategory.WEB_SCRAPING,
    runtime=Runtime.LOCAL_CPU, 
    description="抓取指定公司的最新市場動態與財報摘要。I/O 密集型任務。"
)
async def fetch_market_news(company_symbol: str) -> str:
    print(f"   [CPU 網卡] 🌐 開始並行抓取 {company_symbol} 的資料...")
    await asyncio.sleep(1) # 模擬網路 I/O 耗時
    print(f"   [CPU 網卡] ✅ {company_symbol} 資料下載完成！")
    return f"【{company_symbol} 財報原始資料：營收成長，市場反應熱烈】"


@tool(
    category=DefaultCategory.TEXT_PROCESSING,
    runtime=Runtime.LOCAL_GPU, 
    description="使用地端 GPU 運行開源 LLM，對財報進行深度情緒分析。運算密集且極耗 VRAM。"
)
async def analyze_sentiment_gpu(news_content: str) -> str:
    print(f"   [GPU 核心] 🔥 正在將資料載入 VRAM 進行推論: {news_content[:10]}...")
    await asyncio.sleep(3) # 模擬地端 GPU 推論的漫長耗時
    print(f"   [GPU 核心] 🧊 推論完成，釋放 VRAM。")
    return f"情緒分析結果：極度樂觀 ({news_content[:10]})"


@tool(
    category=DefaultCategory.DATA_ANALYSIS,
    runtime=Runtime.CLOUD_API, 
    description="將多份情緒分析報告統整，透過雲端強大算力生成最終投資策略。需要傳入包含所有分析結果的字串。"
)
async def generate_investment_strategy(all_analyses: str) -> str:
    print(f"   [Cloud API] ☁️ 正在呼叫遠端大模型生成最終策略...")
    await asyncio.sleep(2)
    return "【最終投資組合策略】：重倉 AI 基礎設施，持有晶圓代工龍頭。"


# ==========================================
# 🚀 系統啟動與 Agentic Loop
# ==========================================
async def main():
    print("🚀 啟動 PipelineAgent (資源壓力測試模式)...")

    planner = PipelinePlanner()
    
    # 🌟 核心看點：嚴格的資源管控鎖 (Semaphore)
    engine = AsyncPipelineEngine(resource_limits={
        Runtime.LOCAL_CPU.value: 10,  # 允許 10 條執行緒同時抓網頁
        Runtime.LOCAL_GPU.value: 1,   # ⚠️ 嚴格保護 VRAM！一次只能跑 1 個地端推論
        Runtime.CLOUD_API.value: 5
    })

    # 刻意給 LLM 明確的 Fan-out 指示，強迫它畫出平行處理的 DAG
    # 🌟 真實人類的自然語言指令 (完全不提 DAG、並行或節點)
    user_query = """
    請幫我抓取並深入分析 NVDA, TSMC, AAPL, MSFT, GOOGL 這五家科技巨頭的最新市場動態與財報情緒。
    最後，請根據這五家的情緒分析結果，幫我統整出一份最終的投資策略報告。
    """
    
    print("\n🧠 大腦開始規劃大規模 DAG 藍圖...")
    plan = planner.plan(user_query)
    
    print("\n📋 產出的 DAG 藍圖 (觀察是否有 Fan-out 與 Fan-in):")
    # 這裡印出藍圖可以讓你驗證 LLM 是不是真的畫出了平行架構
    print(plan.model_dump_json(indent=2))

    print("\n=============================================")
    print("⚙️ 引擎開始非同步排程執行 (請觀察終端機輸出的時序)")
    print("=============================================")
    
    start_time = time.time()
    is_success, state, failed = await engine.run(plan)
    elapsed_time = time.time() - start_time

    if is_success:
        print(f"\n🎉 任務大功告成！總耗時: {elapsed_time:.2f} 秒")
        # 如果是循序執行 (ReAct模式)，耗時會是 (1+3)*5 + 2 = 22 秒
        # 在我們的 Pipeline 中，抓取(1秒 並行) + GPU推論(3秒 排隊5次=15秒) + 聚合(2秒) = 理論耗時約 18 秒
        
        # 找出最終節點的結果 (通常是 task_id 裡有 strategy 或 report 的那個)
        for task_id, result in state.items():
            if "strategy" in task_id.lower() or "generate" in task_id.lower():
                print(f"\n📄 最終產出: {result}")
    else:
        print(f"\n❌ 執行失敗，失敗節點: {failed}")

if __name__ == "__main__":
    asyncio.run(main())