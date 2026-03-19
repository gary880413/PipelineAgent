import asyncio

from dotenv import load_dotenv # 🌟 引入 dotenv

# 🌟 在匯入任何其他套件之前，先載入環境變數
load_dotenv()

from pipeline_agent import (
    tool, 
    Runtime, 
    DefaultCategory, 
    PipelinePlanner, 
    AsyncPipelineEngine
)

# --- 1. 工具定義與資源宣告 ---

@tool(
    category=DefaultCategory.WEB_SCRAPING, 
    runtime=Runtime.LOCAL_CPU, 
    description="抓取網頁原始碼。"
)
async def fetch_webpage(url: str) -> str:
    print(f"   [CPU] 正在抓取 {url} ...")
    await asyncio.sleep(1)
    return f"<html>{url} 的冗長原始碼...包含大量雜訊...</html>"

# 🚨 故意設計一個會崩潰的地端 GPU 工具
@tool(
    category=DefaultCategory.TEXT_PROCESSING, 
    runtime=Runtime.LOCAL_GPU, 
    description="使用地端 GPU 快速過濾文本雜訊並濃縮重點。首選工具。"
)
async def local_gpu_summarizer(text: str) -> str:
    print(f"   [GPU] 準備將文本送入本地模型...")
    await asyncio.sleep(1)
    raise RuntimeError("CUDA Out of Memory: 地端 GPU VRAM 不足，推論失敗。")

# ☁️ 雲端備援工具
@tool(
    category=DefaultCategory.TEXT_PROCESSING, 
    runtime=Runtime.CLOUD_API, 
    description="使用雲端 API 過濾文本雜訊並濃縮重點。當 GPU 無法使用時的備援工具。"
)
async def cloud_api_summarizer(text: str) -> str:
    print(f"   [Cloud] 接收到備援請求，正在呼叫遠端模型...")
    await asyncio.sleep(2)
    return "已透過雲端 API 成功濃縮重點：1. 資源排程很重要。 2. 容錯機制是關鍵。"

@tool(
    category=DefaultCategory.DATA_ANALYSIS, 
    runtime=Runtime.CLOUD_API, 
    description="根據重點情報撰寫分析報告。"
)
async def write_report(points: str) -> str:
    print(f"   [Cloud] 正在撰寫最終分析報告...")
    await asyncio.sleep(1)
    return f"最終報告：基於情報 ({points})，我們的架構非常強健。"


# --- 2. 系統啟動與 Agentic Loop ---
async def main():
    user_query = "去抓取 example.com 的網頁，然後幫我把雜訊過濾掉濃縮成重點，最後寫一份分析報告。"
    
    # 1. 初始化 Planner
    planner = PipelinePlanner() 
    
    # 2. 根據當下硬體動態配置資源限制
    custom_limits = {
        Runtime.LOCAL_CPU.value: 20, 
        Runtime.LOCAL_GPU.value: 1,  # 嚴格保護單張顯卡
        Runtime.CLOUD_API.value: 10
    }
    engine = AsyncPipelineEngine(resource_limits=custom_limits) 
    
    # 3. 首次規劃
    current_plan = planner.plan(user_query)
    
    # 4. Agentic Loop (動態容錯重規劃機制)
    max_retries = 3
    attempt = 1
    
    while attempt <= max_retries:
        print(f"\n=============================================")
        print(f"  執行回合 {attempt}/{max_retries}")
        print(f"=============================================")
        
        is_success, current_state, failed_nodes = await engine.run(current_plan)
        
        if is_success:
            print("\n🎉 任務大功告成！")
            break
        else:
            print(f"\n⚠️ 遭遇挫折，Agent 啟動動態重規劃 (準備進入第 {attempt+1} 回合)...")
            # 🌟 核心：將失敗節點交給大腦，讓它生成替代路線 (例如改用 Cloud API)
            current_plan = planner.replan(
                original_goal=user_query,
                current_state=current_state,
                failed_nodes=failed_nodes
            )
            attempt += 1

    # 5. 輸出最終結果
    if not is_success:
        print("\n💀 重試次數耗盡，Agent 放棄任務。")
        
    print("\n[最終全域狀態 (記憶體)]: ")
    for k, v in current_state.items():
        if not isinstance(v, Exception):
            print(f"{k}: {str(v)[:80]}...")

if __name__ == "__main__":
    asyncio.run(main())