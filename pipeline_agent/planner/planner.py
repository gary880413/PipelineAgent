import json
from typing import List
from pydantic import BaseModel, Field
from openai import OpenAI

from pipeline_agent.schemas.schema import DAGPlan, TaskNode
from pipeline_agent.tools.tools import registry
from pipeline_agent.utils.logger import setup_logger
from pipeline_agent.exceptions import RoutingError

logger = setup_logger("pipeline_agent.planner")

# 為第一階段路由準備的臨時 Schema
class CategorySelection(BaseModel):
    selected_categories: List[str] = Field(..., description="挑選出的工具類別列表")

class PipelinePlanner:
    def __init__(self, api_key: str = None):
        self.client = OpenAI(api_key=api_key)
        self.router_model = "gpt-4o-mini"
        self.planner_model = "gpt-4o"

    def _stage_1_route_categories(self, query: str) -> List[str]:
        available_cats = registry.get_all_categories()
        logger.info(f"[Planner Phase 1] 🧠 分析任務: '{query}'")
        
        system_prompt = f"""
        你是一個精準的任務路由系統。
        請分析使用者的任務，並從以下可用類別中，挑選出可能需要用到的工具類別。
        
        可用類別清單: {available_cats}
        """

        response = self.client.beta.chat.completions.parse(
            model=self.router_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ],
            response_format=CategorySelection,
        )
        
        selected = response.choices[0].message.parsed.selected_categories
        logger.debug(f"-> 鎖定類別: {selected}\n")
        return selected

    # 🌟 修正 1：改為接收 active_tools 作為參數，只處理被選中的工具
    def _build_tools_prompt(self, active_tools: List[dict]) -> str:
        """
        將篩選出的工具轉換為 LLM 能夠理解的說明書。
        支援原生 Python Signature 與外部 MCP JSON Schema 兩種格式。
        """
        tools_desc = []
        for info in active_tools:
            name = info["name"]
            
            # 智慧判斷：如果有 MCP Schema，就餵給它 JSON Schema
            if info.get("mcp_schema"):
                schema_str = json.dumps(info["mcp_schema"], ensure_ascii=False)
                desc = (
                    f"- {name} (類別: {info['category']}, 資源: {info['runtime']}):\n"
                    f"  說明: {info['description']}\n"
                    f"  參數格式 (JSON Schema): {schema_str}"
                )
            
            # 否則退回原本的 Python Signature 模式
            else:
                desc = (
                    f"- {name} (類別: {info['category']}, 資源: {info['runtime']}):\n"
                    f"  說明: {info['description']}\n"
                    f"  參數格式 (Python Signature): {info.get('signature', '無')}"
                )
            
            tools_desc.append(desc)
            
        return "\n\n".join(tools_desc)

    def _stage_2_generate_dag(self, query: str, active_tools: List[dict]) -> DAGPlan:
        logger.info(f"[Planner Phase 2] 🧠 構建 DAG 藍圖中 (Model: {self.planner_model})...")
        
        # 🌟 修正 2：正確呼叫智能轉換函式
        tools_description = self._build_tools_prompt(active_tools)

        system_prompt = f"""
        你是一個負責編排非同步流水線 (Pipeline) 的頂級架構師。
        請根據使用者的任務，利用以下提供的工具清單，設計出一個有向無環圖 (DAG) 計畫。

        【效能最佳化規則】
        🌟 如果有多個任務彼此之間沒有依賴關係（例如同時抓取多個不同的網頁、分析多個獨立的檔案），請務必將它們設計為「平行節點」（即 depends_on 為空，或依賴同一個源頭），切勿將它們串聯排隊，以最大化非同步引擎的併發效能。

        【可用工具清單】
        {tools_description}

        【嚴格規則】
        1. 每個步驟 (TaskNode) 必須指定一個唯一且簡短的 task_id。
        2. 如果節點 B 需要等待節點 A 完成，必須在 B 的 `depends_on` 陣列中加入 A 的 task_id。
        3. 如果節點 B 的輸入參數需要使用節點 A 的輸出結果，請在 `tool_inputs_json` 輸出中，使用 `${{task_id.output}}` 的語法進行變數綁定。
        4. 你必須將工具清單中定義的 `runtime` 屬性，原封不動地填入 TaskNode 的 `runtime` 欄位中。
        5. 🌟 在生成 `tool_inputs_json` 時，請嚴格遵守該工具提供的參數格式。若是 Python Signature，請將參數名稱對應為 JSON key；若是 JSON Schema，請務必符合其 properties 與 required 規範。
        """

        response = self.client.beta.chat.completions.parse(
            model=self.planner_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ],
            response_format=DAGPlan,
        )
        
        dag_plan = response.choices[0].message.parsed
        logger.info(f"-> DAG 藍圖生成完畢！(Plan ID: {dag_plan.plan_id})\n")
        return dag_plan

    def plan(self, query: str) -> DAGPlan:
        categories = self._stage_1_route_categories(query)
        if not categories:
            raise RoutingError("找不到合適的工具類別來處理此任務。")
            
        active_tools = registry.get_tools_by_categories(categories)
        return self._stage_2_generate_dag(query, active_tools)
    
    def replan(self, original_goal: str, current_state: dict, failed_nodes: dict) -> DAGPlan:
        logger.warning("\n🚨 [Planner] 收到地端求救信號，啟動動態重規劃 (Re-planning) 🚨")
        
        safe_state = {}
        for k, v in current_state.items():
            if not isinstance(v, Exception):
                val_str = str(v)
                safe_state[k] = val_str[:200] + "..." if len(val_str) > 200 else val_str
                
        query_for_routing = f"目標: {original_goal}. 錯誤: {failed_nodes}"
        categories = self._stage_1_route_categories(query_for_routing)
        if not categories:
            raise RoutingError("找不到合適的工具類別來處理此任務。")
            
        active_tools = registry.get_tools_by_categories(categories)
        
        # 🌟 修正 3：replan 階段也要正確呼叫智能轉換函式
        tools_description = self._build_tools_prompt(active_tools)

        system_prompt = f"""
        你是一個負責災難恢復的 AI 架構師。
        你之前的計畫在執行時遇到了錯誤，你的任務是生成一個【新的、補救用 DAG】來完成原始目標。

        【原始目標】: {original_goal}
        
        【目前已完成的節點與狀態 (你可以直接引用這些結果)】: 
        {json.dumps(safe_state, ensure_ascii=False, indent=2)}
        
        【失敗的節點與錯誤原因】: 
        {json.dumps(failed_nodes, ensure_ascii=False, indent=2)}

        【可用工具清單】:
        {tools_description}

        【嚴格規則】
        1. 不要重新執行已經成功出現在【目前已完成的節點】中的任務。
        2. 你可以直接在 tool_inputs_json 中使用 `${{已完成的task_id.output}}` 來引用既有成果。
        3. 針對失敗的原因，嘗試使用替代工具，或修正輸入參數來繞過錯誤。
        4. 回傳格式必須符合 DAGPlan Schema。
        5. 🌟 在生成 `tool_inputs_json` 時，請嚴格遵守工具說明的參數格式 (Python Signature 或 JSON Schema)。
        """

        logger.info(f"[Planner Phase 2] 🧠 構建補救 DAG 中...")
        response = self.client.beta.chat.completions.parse(
            model=self.planner_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "請生成補救計畫。"}
            ],
            response_format=DAGPlan,
        )
        
        dag_plan = response.choices[0].message.parsed
        logger.info(f"-> 補救 DAG 藍圖生成完畢！(Plan ID: {dag_plan.plan_id})\n")
        return dag_plan