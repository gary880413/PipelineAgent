import json
import logging
from typing import List, Type, Optional
from pydantic import BaseModel, Field
from openai import OpenAI

from pipeline_agent.schemas.schema import DAGPlan, TaskNode
from pipeline_agent.tools.tools import registry
from pipeline_agent.utils.logger import setup_logger
from pipeline_agent.exceptions import RoutingError
from pipeline_agent.config import PipelineConfig

logger = setup_logger("pipeline_agent.planner")

# Temporary schema for stage 1 routing
# 階段 1 路由用的暫時 Schema
class CategorySelection(BaseModel):
    selected_categories: List[str] = Field(..., description="List of selected tool categories")

class PipelinePlanner:
    def __init__(self, config: Optional[PipelineConfig] = None):
        """
        Initialize the Planner with the global configuration.
        使用全局配置初始化規劃者。
        """
        self.config = config or PipelineConfig()
        
        # Lazy initialization for LLM clients based on config
        # 根據配置進行 LLM Client 的延遲初始化
        self._openai_client = None
        if self.config.llm_provider.lower() == "openai":
            # Will automatically look for OPENAI_API_KEY
            # 會自動尋找環境變數 OPENAI_API_KEY
            self._openai_client = OpenAI() 
            
    def _get_system_prompt_prefix(self) -> str:
        """
        Inject the user-defined custom prompt as a Persona/Role descriptor, 
        without conflicting with the framework's core structural instructions.
        將使用者自訂的 prompt 作為角色/人格補述注入，且不與框架核心結構指令衝突。
        """
        return f"[User Defined Persona]\n{self.config.system_prompt}\n\n[Framework Instructions]\n"

    def _dispatch_parsed_llm_request(
        self, 
        model_name: str, 
        system_prompt: str, 
        user_prompt: str, 
        response_model: Type[BaseModel]
    ) -> BaseModel:
        """
        Centralized LLM router that supports structured outputs.
        支援結構化輸出的集中式 LLM 路由分配器。
        """
        provider = self.config.llm_provider.lower()
        
        if provider == "openai":
            if not self._openai_client:
                self._openai_client = OpenAI()
            response = self._openai_client.beta.chat.completions.parse(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format=response_model,
                temperature=0.1
            )
            return response.choices[0].message.parsed
            
        elif provider == "anthropic":
            # TODO: Implement Anthropic's tool use for structured output
            # 待辦：實作 Anthropic 的工具呼叫以支援結構化輸出
            raise NotImplementedError("Anthropic structured parsing is planned for future releases. / 未來版本將支援 Anthropic 結構化解析。")
        else:
            raise ValueError(f"Unsupported LLM provider / 尚不支援的 LLM 供應商: {provider}")

    def _stage_1_route_categories(self, query: str) -> List[str]:
        available_cats = registry.get_all_categories()
        logger.info(f"[Planner Phase 1] 🧠 Analyzing task: '{query}'")
        
        # Combine User Persona + Phase 1 Logic
        # 結合使用者角色 + 階段 1 邏輯
        system_prompt = self._get_system_prompt_prefix() + f"""
        You are a precise task routing system.
        Please analyze the user's task and select the tool categories that may be needed from the available categories below.
        
        Available categories: {available_cats}
        """

        parsed_response = self._dispatch_parsed_llm_request(
            model_name=self.config.model_name, 
            system_prompt=system_prompt,
            user_prompt=query,
            response_model=CategorySelection
        )
        
        selected = parsed_response.selected_categories
        logger.debug(f"-> Selected categories: {selected}\n")
        return selected

    def _build_tools_prompt(self, active_tools: List[dict]) -> str:
        """
        Convert the filtered tools into a manual that the LLM can understand.
        Supports both native Python Signature and external MCP JSON Schema formats.
        將過濾後的工具轉換為 LLM 能理解的手冊。
        支援原生的 Python Signature 與外部的 MCP JSON Schema 格式。
        """
        tools_desc = []
        for info in active_tools:
            name = info["name"]
            
            # Smart detection: If there is an MCP Schema, provide the JSON Schema
            # 智慧偵測：若存在 MCP Schema，則提供 JSON Schema
            if info.get("mcp_schema"):
                schema_str = json.dumps(info["mcp_schema"], ensure_ascii=False)
                desc = (
                    f"- {name} (Category: {info['category']}, Runtime: {info['runtime']}):\n"
                    f"  Description: {info['description']}\n"
                    f"  Parameter format (JSON Schema): {schema_str}"
                )
            # Otherwise, fall back to the original Python Signature mode
            # 否則，退回原始的 Python Signature 模式
            else:
                desc = (
                    f"- {name} (Category: {info['category']}, Runtime: {info['runtime']}):\n"
                    f"  Description: {info['description']}\n"
                    f"  Parameter format (Python Signature): {info.get('signature', 'None')}"
                )
            
            tools_desc.append(desc)
            
        return "\n\n".join(tools_desc)

    def _stage_2_generate_dag(self, query: str, active_tools: List[dict]) -> DAGPlan:
        logger.info(f"[Planner Phase 2] 🧠 Building DAG blueprint (Model: {self.config.model_name})...")
        
        tools_description = self._build_tools_prompt(active_tools)

        # Combine User Persona + Phase 2 Logic
        # 結合使用者角色 + 階段 2 邏輯
        system_prompt = self._get_system_prompt_prefix() + f"""
        You are a top architect responsible for orchestrating asynchronous pipelines.
        Based on the user's task, use the provided tool list below to design a Directed Acyclic Graph (DAG) plan.

        [Performance Optimization Rules]
        🌟 If there are multiple tasks that do not depend on each other (e.g., fetching different web pages or analyzing independent files simultaneously), be sure to design them as "parallel nodes" (i.e., depends_on is empty or depends on the same source), and do not chain them in sequence, to maximize the concurrency of the asynchronous engine.

        [Available Tools]
        {tools_description}

        [Strict Rules]
        1. Each step (TaskNode) must specify a unique and concise task_id.
        2. If node B needs to wait for node A to complete, B's `depends_on` array must include A's task_id.
        3. If node B's input parameters need to use the output of node A, use the `${{task_id.output}}` syntax for variable binding in `tool_inputs_json`.
        4. You must copy the `runtime` property defined in the tool list directly into the TaskNode's `runtime` field.
        5. 🌟 When generating `tool_inputs_json`, strictly follow the parameter format provided by the tool. For Python Signature, map parameter names to JSON keys; for JSON Schema, strictly comply with its properties and required specifications.
        """

        dag_plan = self._dispatch_parsed_llm_request(
            model_name=self.config.model_name,
            system_prompt=system_prompt,
            user_prompt=query,
            response_model=DAGPlan
        )
        
        logger.info(f"-> DAG blueprint generated! (Plan ID: {dag_plan.plan_id})\n")
        return dag_plan

    def plan(self, query: str) -> DAGPlan:
        categories = self._stage_1_route_categories(query)
        if not categories:
            raise RoutingError("No suitable tool categories found to handle this task. / 找不到適合處理此任務的工具類別。")
            
        active_tools = registry.get_tools_by_categories(categories)
        return self._stage_2_generate_dag(query, active_tools)
    
    def replan(self, original_goal: str, current_state: dict, failed_nodes: dict) -> DAGPlan:
        logger.warning("\n🚨 [Planner] Received emergency signal, initiating dynamic re-planning 🚨")
        
        safe_state = {}
        for k, v in current_state.items():
            if not isinstance(v, Exception):
                val_str = str(v)
                safe_state[k] = val_str[:200] + "..." if len(val_str) > 200 else val_str
                
        query_for_routing = f"Goal: {original_goal}. Error: {failed_nodes}"
        categories = self._stage_1_route_categories(query_for_routing)
        if not categories:
            raise RoutingError("No suitable tool categories found to handle this task. / 找不到適合處理此任務的工具類別。")
            
        active_tools = registry.get_tools_by_categories(categories)
        tools_description = self._build_tools_prompt(active_tools)

        # Combine User Persona + Replan Logic
        # 結合使用者角色 + 重新規劃邏輯
        system_prompt = self._get_system_prompt_prefix() + f"""
        You are an AI architect responsible for disaster recovery.
        Your previous plan encountered errors during execution. Your task is to generate a [new, remedial DAG] to accomplish the original goal.

        [Original Goal]: {original_goal}
        
        [Currently completed nodes and states (you can directly reference these results)]: 
        {json.dumps(safe_state, ensure_ascii=False, indent=2)}
        
        [Failed nodes and error reasons]: 
        {json.dumps(failed_nodes, ensure_ascii=False, indent=2)}

        [Available Tools]:
        {tools_description}

        [Strict Rules]
        1. Do not re-execute tasks that have already succeeded and appear in [Currently completed nodes].
        2. You can directly use `${{completed_task_id.output}}` in tool_inputs_json to reference existing results.
        3. For the causes of failure, try to use alternative tools or modify input parameters to bypass the error.
        4. The return format must comply with the DAGPlan Schema.
        5. 🌟 When generating `tool_inputs_json`, strictly follow the parameter format described in the tool (Python Signature or JSON Schema).
        """

        logger.info(f"[Planner Phase 2] 🧠 Building remedial DAG...")
        
        dag_plan = self._dispatch_parsed_llm_request(
            model_name=self.config.model_name,
            system_prompt=system_prompt,
            user_prompt="Please generate a remedial plan. / 請生成補救計畫。",
            response_model=DAGPlan
        )
        
        logger.info(f"-> Remedial DAG blueprint generated! (Plan ID: {dag_plan.plan_id})\n")
        return dag_plan