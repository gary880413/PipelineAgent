import json
from typing import List
from pydantic import BaseModel, Field
from openai import OpenAI

from pipeline_agent.schemas.schema import DAGPlan, TaskNode
from pipeline_agent.tools.tools import registry
from pipeline_agent.utils.logger import setup_logger
from pipeline_agent.exceptions import RoutingError

logger = setup_logger("pipeline_agent.planner")

# Temporary schema for stage 1 routing
class CategorySelection(BaseModel):
    selected_categories: List[str] = Field(..., description="List of selected tool categories")

class PipelinePlanner:
    def __init__(self, api_key: str = None):
        self.client = OpenAI(api_key=api_key)
        self.router_model = "gpt-4o-mini"
        self.planner_model = "gpt-4o"

    def _stage_1_route_categories(self, query: str) -> List[str]:
        available_cats = registry.get_all_categories()
        logger.info(f"[Planner Phase 1] 🧠 Analyzing task: '{query}'")
        
        system_prompt = f"""
        You are a precise task routing system.
        Please analyze the user's task and select the tool categories that may be needed from the available categories below.
        
        Available categories: {available_cats}
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
        logger.debug(f"-> Selected categories: {selected}\n")
        return selected

    # 🌟 Fix 1: Accept active_tools as a parameter, only process selected tools
    def _build_tools_prompt(self, active_tools: List[dict]) -> str:
        """
        Convert the filtered tools into a manual that the LLM can understand.
        Supports both native Python Signature and external MCP JSON Schema formats.
        """
        tools_desc = []
        for info in active_tools:
            name = info["name"]
            
            # Smart detection: If there is an MCP Schema, provide the JSON Schema
            if info.get("mcp_schema"):
                schema_str = json.dumps(info["mcp_schema"], ensure_ascii=False)
                desc = (
                    f"- {name} (Category: {info['category']}, Runtime: {info['runtime']}):\n"
                    f"  Description: {info['description']}\n"
                    f"  Parameter format (JSON Schema): {schema_str}"
                )
            
            # Otherwise, fall back to the original Python Signature mode
            else:
                desc = (
                    f"- {name} (Category: {info['category']}, Runtime: {info['runtime']}):\n"
                    f"  Description: {info['description']}\n"
                    f"  Parameter format (Python Signature): {info.get('signature', 'None')}"
                )
            
            tools_desc.append(desc)
            
        return "\n\n".join(tools_desc)

    def _stage_2_generate_dag(self, query: str, active_tools: List[dict]) -> DAGPlan:
        logger.info(f"[Planner Phase 2] 🧠 Building DAG blueprint (Model: {self.planner_model})...")
        
        # 🌟 Fix 2: Correctly call the smart conversion function
        tools_description = self._build_tools_prompt(active_tools)

        system_prompt = f"""
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

        response = self.client.beta.chat.completions.parse(
            model=self.planner_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ],
            response_format=DAGPlan,
        )
        
        dag_plan = response.choices[0].message.parsed
        logger.info(f"-> DAG blueprint generated! (Plan ID: {dag_plan.plan_id})\n")
        return dag_plan

    def plan(self, query: str) -> DAGPlan:
        categories = self._stage_1_route_categories(query)
        if not categories:
            raise RoutingError("No suitable tool categories found to handle this task.")
            
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
            raise RoutingError("No suitable tool categories found to handle this task.")
            
        active_tools = registry.get_tools_by_categories(categories)
        
        # 🌟 Fix 3: Also correctly call the smart conversion function in the replan stage
        tools_description = self._build_tools_prompt(active_tools)

        system_prompt = f"""
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
        response = self.client.beta.chat.completions.parse(
            model=self.planner_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Please generate a remedial plan."}
            ],
            response_format=DAGPlan,
        )
        
        dag_plan = response.choices[0].message.parsed
        logger.info(f"-> Remedial DAG blueprint generated! (Plan ID: {dag_plan.plan_id})\n")
        return dag_plan