# PipelineAgent 階段性審視與下一步開發路線圖

> 撰寫日期：2026-05-05
> 對應版本：`v0.2.0`（HEAD = `features/Flexibility` @ `098143b`）
> 對照基線：`origin/develop` @ `3a25c95`

本文件目的有二：
1. **階段性盤點**：把目前專案的概念、架構契約、實作完成度、未實作但已暗示存在的能力一次梳理清楚。
2. **挖掘 `features/Flexibility` 分支尚未榨乾的機會**：列出可立即接續、無須改動 `architecture_and_semantics.md` 既有契約即可落地的功能。

---

## 1. 專案概念與架構回顧

### 1.1 設計哲學
PipelineAgent 拒絕傳統 ReAct 式「單步迴圈 + LLM 重複決策」的範式，改採 **Plan-Once / Execute-Many** 架構：

- **Cloud Brain（Planner）**：只負責把使用者意圖一次性轉成 DAG 藍圖（`DAGPlan` / `TaskNode`）。
- **Edge Engine（AsyncPipelineEngine）**：純粹的 asyncio 排程器，負責拓撲解析、變數注入、Semaphore 級資源隔離、快照與失敗封鎖。
- **MCP 為一等公民**：`MCPClientManager` 把外部 stdio MCP server 動態掛載成本地 Tool，並指派獨立 runtime 鎖。

### 1.2 系統契約（已在 `architecture_and_semantics.md` 鎖定）
| 契約 | 內容摘要 |
| --- | --- |
| 排程策略 | Topological Sort + Greedy + 每 runtime 一把 `asyncio.Semaphore`，FIFO |
| 變數注入 | 僅做字串替換 `${node_id.output}`，型別轉換留給 Tool 內 `pydantic` |
| 節點狀態機 | `PENDING → RUNNING → SUCCESS / FAILED / CANCELLED_DUE_TO_UPSTREAM` |
| 冪等性 | Engine 持久化成功節點輸出；同 `plan_id` 再執行直接讀檔，**不重跑** Tool |
| 失敗封鎖 | 禁止 `asyncio.Task.cancel()`；用 DAG 反向掃描標記下游 `CANCELLED` |
| 補救 DAG | 不從零開始；與既有 state 做 context merge，只重排失敗 + 殘餘子圖 |

### 1.3 模組地形圖
```
pipeline_agent/
├── config.py         ← v0.2.0 新增：PipelineConfig（全域配置中心）
├── core.py           ← (尚未閱讀；推測為高階入口或保留)
├── exceptions.py     ← 自訂錯誤族群（DependencyResolutionError / ToolExecutionError / MCPCallError ...）
├── schemas/schema.py ← Runtime / NodeState / TaskNode / DAGPlan / EngineResult
├── tools/tools.py    ← @tool 裝飾器 + ToolRegistry + register_direct（給 MCP 用）
├── planner/planner.py← 兩階段規劃（Route Categories → Build DAG）+ replan
├── engine/engine.py  ← Async DAG runner + checkpoint + trace export
├── mcp/client.py     ← MCPClientManager（stdio 連線 + 代理函式 + 動態註冊）
└── utils/
    ├── checkpoint.py ← 每個 plan_id 一個資料夾的 JSON 狀態檔
    └── logger.py
```

### 1.4 已實作完成度（與 README Roadmap 對照後校正）
| 能力 | README 標示 | 實際盤點 |
| --- | --- | --- |
| DAG 生成 | 🟢 | ✅ 兩階段 routing + structured outputs |
| Async Engine | 🟢 | ✅ 但 `engine.py` 內存在**重複定義的 `run()` 方法**（後者覆蓋前者，前者為死碼） |
| Resource Isolation | 🟢 | ✅ 透過 `PipelineConfig.default_resource_limits` 提供預設 |
| MCP 整合 | 🟢 | ✅ 已支援 `category` 客製化、JSON Schema 透傳給 Planner |
| Error Halting | 🟢 | ✅ `_halt_downstream_nodes` 遞迴 + `try/finally` 釋放 event |
| Self-Healing | 🟡 | ⚠️ `replan` 已實作；但**外迴圈在 example 內**而非 framework 內 |
| Semantic Tool Retrieval | ⚪ | 尚未動工（仍是 brute-force category 過濾） |
| State/Memory Persistence | ⚪ | Checkpoint 已存在但僅用於同 `plan_id` 重跑，跨 session 記憶尚未抽象化 |

---

## 2. `features/Flexibility` 分支現況解析

### 2.1 此分支已交付的「彈性」
3 個 commit、5 檔變動，核心成果為：

1. **`PipelineConfig` 全域配置中心**（`d1c19bc`）
   - 抽出 `llm_provider` / `model_name` / `system_prompt` / `workspace_dir` /
     `enable_tracing` / `enable_checkpointing` / `node_timeout_sec` / `default_resource_limits`。
   - `AsyncPipelineEngine.__init__` 接受 `config` 與 `resource_limits`，後者覆寫前者。
2. **MCP 跨平台啟動**（`cbac7bd`）
   - `examples/mcp_agent_demo.py` 改用 `sys.executable -m mcp_server_fetch`，
     Windows 上不再依賴 PATH 中的 `mcp-server-fetch.exe`。
3. **Planner LLM 路由抽象**（`098143b`）
   - 新增 `_dispatch_parsed_llm_request()` 集中分配。
   - 引入 `_get_system_prompt_prefix()`，把使用者自訂 prompt 注成 **Persona**，
     不污染框架核心結構指令。
   - 為 `anthropic` 預留分支（目前 `NotImplementedError`）。

### 2.2 「Flexibility」分支還能挖什麼？（關鍵發現）
以下是審視程式碼後**真正存在落地空間**的工作項。它們都符合分支主題（彈性 / 兼容性），且**不違反 `architecture_and_semantics.md` 既定契約**。

#### 🥇 P0：宣告了卻沒接線的 Config 欄位
- **`node_timeout_sec` 形同虛設**
  `config.py` 定義了預設 120 秒，但 `engine._execute_node()` 內找不到任何 `asyncio.wait_for(...)` 包裹 Tool 呼叫。
  **建議**：用 `await asyncio.wait_for(func(...), timeout=self.config.node_timeout_sec)` 包住 `func` 執行段落，超時後拋 `ToolExecutionError(..., original_error=TimeoutError(...))`，自然走既有的 `FAILED → halt downstream` 流程，完全相容契約 §3。
- **`enable_tracing` / `enable_checkpointing` 環境變數覆寫缺失**
  目前只能由程式碼傳入 `PipelineConfig(...)`。建議讓 `PipelineConfig` 同時支援
  `model_config = SettingsConfigDict(env_prefix="PIPELINE_")`（升級成 `pydantic-settings`），
  讓 CI / Docker 場景能用環境變數開關。

#### 🥈 P1：LLM Provider 兼容性（分支主題本身）
- **Anthropic / Ollama / Azure OpenAI 真的接起來**
  `_dispatch_parsed_llm_request` 已是漂亮的 strategy 點。建議：
  - Anthropic：用 `anthropic` SDK 的 `tool_use` 模擬 structured output（把 Pydantic schema → JSON Schema → tool）。
  - Ollama：透過 `openai` SDK 的 `base_url=http://localhost:11434/v1` 即可重用同一條路徑，**幾乎零成本**。
  - Azure OpenAI：同樣只是改 `client = AzureOpenAI(...)`。
- **Async LLM client**
  `Planner.plan()` 目前是 sync 呼叫，整個事件迴圈被 LLM 阻塞。改成 `AsyncOpenAI` + `await planner.plan()`
  可大幅降低混合 workload 下的延遲。

#### 🥉 P2：Tool 層彈性
- **`@tool` 裝飾器目前只吃 `DefaultCategory.*` 字串常數**，但 `register_direct` 已接受任意字串（MCP 路徑用）。
  建議讓 `@tool(category=...)` 也接受 `str`，與 MCP 對齊，方便使用者自訂業務分類（如 `"FinancialReport"`）。
- **Tool 級別 timeout / retry override**
  `@tool(timeout=30, max_retries=2)`，由 Engine 在執行時優先採用，找不到才回落到 `PipelineConfig.node_timeout_sec`。
- **Tool input 型別反射**
  目前 Planner 把 `inspect.signature(func)` 的字串塞給 LLM。改用 `pydantic.TypeAdapter` 從 type hints 產 JSON Schema，與 MCP 路徑統一，能讓 LLM 產更準確的 `tool_inputs_json`。

#### 🏅 P3：Engine 重構與 bug fix（順手）
- **`engine.py` 內 `run()` 重複定義**（檔案末端有兩個 `async def run`）。第二個覆蓋第一個，導致第一段約 25 行為死碼。應刪除第一個。
- **`schemas/schema.py` 內 `NodeState` Enum 類別體底下誤植**：
  ```python
  start_time: Optional[float] = None
  end_time: Optional[float] = None
  ```
  這兩行寫在 `NodeState(str, Enum)` 內，會被當成 enum member 嘗試而失效，明顯是從 `TaskNode` 誤剪到此處，應移除。
- **`_resolve_inputs` 對 list 的處理**用 `{"temp": item}` 包一層 hack，可改寫為直接遞迴函式，提升可讀性與正確性。

#### 🎯 P4：對外契約相容性
- **`PipelineConfig.from_yaml(path)` / `from_toml(path)`**
  讓使用者能用宣告式檔案描述 LLM、resource、prompt，呼應「Macro-Pipeline Architect」精神。
- **`AGENTS.md` / 一份 MCP server 推薦清單**
  目前 README 只示範 `mcp-server-fetch` 與 `@modelcontextprotocol/server-filesystem`。可加一份「驗證過可直接掛載」的清單，是分支主題（兼容性）最直觀的對外輸出。

---

## 3. 階段性路線圖建議

依「投入/回報比」與「是否立即解鎖新能力」排序：

### Phase A（✅ 已完成）
- [x] **A1** 接線 `node_timeout_sec`（`asyncio.wait_for` 包裹 Tool 執行）
- [x] **A2** 修 `engine.run` 重複定義 + `NodeState` Enum 誤植
- [x] **A3** Ollama / Azure OpenAI / OpenAI-compatible 走統一 SDK 端點
- [x] **A4** `@tool(category=str)` 放寬型別 + `Tool` 級 `timeout` override
- [x] **A5** `examples/llm_provider_switch.py`：示範多 provider 切換

### Phase B（下一個 minor 版本 v0.3.0）
- [x] **B1** Async Planner（`AsyncOpenAI` / `AsyncAzureOpenAI`），`plan()` / `replan()` 全面 async 化
- [x] **B2** Anthropic structured output 真實作（透過 `tool_use` + `tool_choice` 強制呼叫機制）
- [x] **B3** `pydantic-settings` 化 `PipelineConfig`（環境變數 `PIPELINE_*` / `.env` 自動載入）
- [x] **B4** Self-healing agentic loop 抽出為**獨立編排層** `AgenticRunner(planner, engine).run(query, max_retries)`
  - ⚠️ 設計修正紀錄：初版誤把此能力放進 `engine.run_with_healing()`，違反「Planner 交付 DAG 後 Engine 不再回呼 Planner」的單向依賴契約。已重構為獨立的 `pipeline_agent/runner.py` 編排層，Planner / Engine 之間維持嚴格解耦。

### Phase C（中長期，呼應 Roadmap 的 ⚪）
- [ ] **C1** Semantic Tool Retrieval：以 sqlite-vss 或 chromadb 取代 brute-force 分類路由
- [ ] **C2** State / Memory Persistence：`CheckpointManager` 抽象成 `ArtifactStore` 介面，
       提供 `LocalFSStore` / `S3Store` / `RedisStore` 實作，跨 session 共享
- [ ] **C3** Trace 視覺化：把 `traces/*.json` 餵給簡易 web viewer（可走 `mermaid` gantt / `pyvis`）
- [ ] **C4** Benchmark 標準化：把 `benchmarks/langchain_vs_pipeline.py` 拓展為跨 framework 矩陣（含 LangGraph、CrewAI）

### Phase T（測試補完，可與任一 Phase 並行）
> 目前現況：`tests/test_engine.py` 僅 2 個測試（checkpoint + halting），
> `examples/*.py` 皆為情境式 demo 而非單元測試，CI 上的 merge gate 覆蓋率不足。
- [ ] **T1** `Planner` 單元測試：mock LLM client，驗證 `plan` / `replan` 的 routing → DAG 流程
- [ ] **T2** `_anthropic_structured_request` 測試：mock `AsyncAnthropic.messages.create`，驗證 tool_use 解析
- [ ] **T3** Multi-provider `_init_llm_client` 測試：四種 provider × Azure / Ollama 預設值矩陣
- [ ] **T4** `AgenticRunner` 測試：mock planner + engine，驗證成功路徑、失敗重試、達上限放棄
- [ ] **T5** `PipelineConfig` 測試：env var 覆寫、`.env` 載入、`PIPELINE_` 前綴隔離
- [ ] **T6** Engine timeout 測試：`asyncio.wait_for` 超時觸發 FAILED → 下游 CANCELLED
- [ ] **T7** Tool registry 測試：`@tool` 註冊、`register_direct`（MCP 路徑）、category filtering
- [ ] **T8** GitHub Actions CI gate 強化：所有 PR 必須通過 T1–T7，並要求最低覆蓋率（建議 70%）

---

## 4. 風險與技術債紀錄

| 項目 | 風險 | 建議處置 |
| --- | --- | --- |
| ~~`engine.py` 雙 `run()` 定義~~ | ~~任何後續 PR 易誤改舊版導致行為飄移~~ | ✅ Phase A2 已刪除 |
| ~~`NodeState` Enum 誤植~~ | ~~雖目前不報錯，但若後續啟用 `mypy --strict` 會炸~~ | ✅ Phase A2 已移除 |
| `_dispatch_parsed_llm_request` 只支援 `parse` | 未來要加 streaming / tool-use 時需大改 | ⚠️ 部分緩解：B2 已用 tool_use 為 Anthropic 走獨立分支；若未來要加 streaming 仍建議重構為策略類別 |
| **單元測試覆蓋率不足** | `tests/` 僅 2 個 case，examples 皆為情境式 demo；CI merge gate 形同虛設 | Phase T 系統性補完（T1–T8）|
| `MCPClientManager.connect_and_register` 失敗時只 `logger.error` 不 raise | 上游無從得知掛載失敗 | 補上 `raise MCPConnectionError(...)` |
| `_resolve_inputs` 對 nested list 採 dict-wrap hack | 維護性差 | 後續重寫 |

---

## 5. 結語

`features/Flexibility` 分支已經把「全域配置 + LLM 路由抽象」的骨架搭好，這是讓 PipelineAgent 從「OpenAI 專屬玩具」走向「多後端通用框架」的關鍵跳板。
**真正能榨乾此分支價值的接續動作**，是把 §2.2 P0 / P1 的項目補完——它們都不需要動到 `architecture_and_semantics.md` 既有契約，純粹是把「已宣告但未接線」的能力兌現，是當下 ROI 最高的工作。
