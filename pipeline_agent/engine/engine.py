import os
import asyncio
import re
from typing import Dict, Any, Optional
import json
import inspect 
import time

from pipeline_agent.schemas.schema import DAGPlan, TaskNode, EngineResult, Runtime, NodeState
from pipeline_agent.tools.tools import registry
from pipeline_agent.exceptions import DependencyResolutionError, ToolExecutionError
from pipeline_agent.config import PipelineConfig

from pipeline_agent.utils.logger import setup_logger
logger = setup_logger("pipeline_agent.planner")

from pipeline_agent.utils.checkpoint import CheckpointManager

class AsyncPipelineEngine:
    def __init__(self, config: Optional[PipelineConfig] = None, resource_limits: Optional[Dict[str, int]] = None):
        """
        Initialize the engine with configuration and optional resource overrides.
        初始化引擎，載入配置與可選的資源限制覆寫。
        """
        self.state: Dict[str, Any] = {}
        self.events: Dict[str, asyncio.Event] = {}
        
        # 1. Apply config (use default if not provided)
        # 1. 套用配置 (若未提供則使用預設值)
        self.config = config or PipelineConfig()
        
        # 2. Merge resource limits (User override > Config default)
        # 2. 合併資源限制 (使用者覆寫 > 配置預設值)
        final_limits = self.config.default_resource_limits.copy()
        if resource_limits:
            final_limits.update(resource_limits)
            
        self.resource_locks = {
            k: asyncio.Semaphore(v) for k, v in final_limits.items()
        }

        # 3. Setup checkpoint directory based on config
        # 3. 根據配置設定快照目錄
        checkpoint_dir = os.path.join(self.config.workspace_dir, "checkpoints")
        self.checkpoint_manager = CheckpointManager(base_dir=checkpoint_dir)

    def _resolve_inputs(self, inputs: dict, state: dict) -> dict:
        """
        Replace ${task_id.output} in input parameters with actual state values.
        Supports single variable replacement (preserves original type) and string interpolation (multiple variables).
        """
        resolved = {}
        for k, v in inputs.items():
            if isinstance(v, str):
                # Case A: The entire string is a variable (e.g., "${step_1.output}"), preserve original type (could be Dict/List)
                full_match = re.fullmatch(r'\$\{([^}]+)\.output\}', v)
                if full_match:
                    task_id = full_match.group(1)
                    if task_id not in state:
                        raise DependencyResolutionError(f"Dependency output for {task_id} not found in state.")
                    resolved[k] = state[task_id]
                    continue

                # Case B: String interpolation (e.g., "NVDA: ${nvda.output}, TSMC: ${tsmc.output}")
                def replacer(match):
                    task_id = match.group(1)
                    if task_id not in state:
                        raise DependencyResolutionError(f"Dependency output for {task_id} not found in state.")
                    return str(state[task_id])
                
                # Replace all occurrences of ${xxx.output} in the string
                resolved_str = re.sub(r'\$\{([^}]+)\.output\}', replacer, v)
                resolved[k] = resolved_str
            
            elif isinstance(v, dict):
                # Recursively process nested dictionaries
                resolved[k] = self._resolve_inputs(v, state)
            elif isinstance(v, list):
                # Process arrays
                resolved[k] = [self._resolve_inputs({"temp": item}, state)["temp"] for item in v]
            else:
                resolved[k] = v
                
        return resolved

    async def _execute_node(self, plan: DAGPlan, node: TaskNode, current_state: dict) -> Any:
        # 🚨 Fix 1: Wrap the entire function lifecycle in Try-Finally to ensure downstream locks are always released
        try:
            # ==========================================
            # 1. Asynchronously wait for upstream dependencies to complete (Synchronization)
            # ==========================================
            if node.depends_on:
                logger.info(f"[{node.task_id}] ⏳ Waiting for dependencies: {node.depends_on}")
                for dep in node.depends_on:
                    # 🚨 Fix 2: Cross-round dependency check. If the upstream result is already in state, it means it succeeded previously, so no need to wait!
                    if dep in current_state:
                        continue
                    
                    # Prevent phantom dependencies: If not found in state and not in current DAG events, raise error immediately
                    if dep not in self.events:
                        raise DependencyResolutionError(f"Dependency '{dep}' missing in both state and DAG.")
                        
                    await self.events[dep].wait()
                    
            # 🚨 Guard 1.5: After being awakened, immediately check if this node has been cancelled due to upstream failure
            if node.state == NodeState.CANCELLED_DUE_TO_UPSTREAM:
                logger.warning(f"[{node.task_id}] ⏭️ Skipped execution because this node was marked as cancelled due to upstream failure.")
                return None

            # 🚨 Guard 2: Check snapshot, implement Exactly-Once (idempotency)
            if self.config.enable_checkpointing:
                cached_output = self.checkpoint_manager.get_node_output(plan.plan_id, node.task_id)
                if cached_output is not None:
                    logger.info(f"[{node.task_id}] ♻️ Found historical snapshot, skipping computation and loading result directly.")
                    node.state = NodeState.SUCCESS
                    current_state[node.task_id] = cached_output
                    return cached_output

            # Officially mark as running
            node.state = NodeState.RUNNING
            node.start_time = time.time()

            # ==========================================
            # 2. Resource pool queuing and locking (Semaphore Lock)
            # ==========================================
            lock = self.resource_locks.get(node.runtime, asyncio.Semaphore(1))
            logger.info(f"[{node.task_id}] 🚥 Queuing in [{node.runtime.upper()}] resource pool...")

            async with lock:
                logger.info(f"[{node.task_id}] 🚀 Acquired [{node.runtime.upper()}] execution right! Starting computation...")
                
                raw_inputs = json.loads(node.tool_inputs_json)
                resolved_inputs = self._resolve_inputs(raw_inputs, current_state)
                
                tool_info = registry._tools.get(node.tool_name)
                if not tool_info:
                    raise ToolExecutionError(task_id=node.task_id, tool_name=node.tool_name, original_error=Exception(f"Tool '{node.tool_name}' not found in registry."))
                    
                func = tool_info["callable"]
                safe_log_inputs = {k: (str(v)[:50] + "..." if isinstance(v, str) and len(str(v)) > 50 else v) for k, v in resolved_inputs.items()}
                logger.info(f"[{node.task_id}] Calling '{node.tool_name}' with params: {safe_log_inputs}")
                
                if inspect.iscoroutinefunction(func):
                    result = await func(**resolved_inputs)
                else:
                    result = await asyncio.to_thread(func, **resolved_inputs)
                
                logger.info(f"[{node.task_id}] ✅ Task completed, releasing [{node.runtime.upper()}] resource!")

                # 🚨 Guard 3: On successful execution, force save snapshot
                if self.config.enable_checkpointing:
                    self.checkpoint_manager.save_node_output(plan.plan_id, node.task_id, result)
                node.state = NodeState.SUCCESS
                node.end_time = time.time()
                current_state[node.task_id] = result
                return result

        except Exception as e:
            # 🚨 Guard 4: Catch any crash (including KeyError or TypeError), trigger downstream blocking
            logger.error(f"[{node.task_id}] ❌ Execution failed: {str(e)}")
            node.state = NodeState.FAILED
            node.end_time = time.time()
            self._halt_downstream_nodes(plan, failed_node_id=node.task_id)
            raise ToolExecutionError(task_id=node.task_id, tool_name=node.tool_name, original_error=e)  
            
        finally:
            # 🚨 Guard 5: This line is now protected; no matter what happens, it will always execute, completely eliminating deadlocks!
            self.events[node.task_id].set()

    def _export_trace(self, plan: DAGPlan):
        """Export execution trace as JSON for visualization and analysis"""

        if not self.config.enable_tracing:
            return

        trace_dir = os.path.join(self.config.workspace_dir, "traces")
        os.makedirs(trace_dir, exist_ok=True)
        trace_file = os.path.join(trace_dir, f"trace_{plan.plan_id}.json")

        trace_data = {
            "plan_id": plan.plan_id,
            "goal": plan.goal,
            "nodes": {}
        }
        
        for node in plan.nodes:
            duration = None
            if node.start_time and node.end_time:
                duration = round(node.end_time - node.start_time, 4)
                
            trace_data["nodes"][node.task_id] = {
                "tool": node.tool_name,
                "runtime": node.runtime,
                "state": node.state.value,
                "duration_sec": duration
            }

        with open(trace_file, "w", encoding="utf-8") as f:
            json.dump(trace_data, f, indent=2, ensure_ascii=False)
            
        logger.info(f"📊 Pipeline Execution Trace exported to: {trace_file}")


    def _halt_downstream_nodes(self, plan: DAGPlan, failed_node_id: str):
        """Recursively scan the DAG and mark all nodes depending on failed_node_id as CANCELLED"""
        for node in plan.nodes:
            # If this node has not been executed yet, and its dependencies include the failed node
            if node.state == NodeState.PENDING and failed_node_id in node.depends_on:
                node.state = NodeState.CANCELLED_DUE_TO_UPSTREAM
                logger.warning(f"[{node.task_id}] 🛑 Marked as cancelled due to upstream '{failed_node_id}' failure.")
                # Recursive blocking: since this node is cancelled, its downstream nodes must also be cancelled
                self._halt_downstream_nodes(plan, failed_node_id=node.task_id)

    async def run(self, dag: DAGPlan) -> EngineResult: 
        logger.info(f"\n=== Starting Pipeline Engine (Plan: {dag.plan_id}) ===\n")
        
        # Ensure old events are cleared to avoid cross-plan contamination
        self.events.clear()
        for node in dag.nodes:
            self.events[node.task_id] = asyncio.Event()

        # 🚨 Fix 1: Pass correct parameters (plan, node, current_state)
        tasks = [
            asyncio.create_task(self._execute_node(plan=dag, node=node, current_state=self.state)) 
            for node in dag.nodes
        ]
        
        # 🚨 Fix 2: Add return_exceptions=True to protect parallel branches
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 🚨 Fix 3: Use state machine (NodeState) to determine failed nodes, not just exceptions
        failed_nodes = {}
        for node, task_result in zip(dag.nodes, results):
            if node.state == NodeState.FAILED:
                # Exceptions caught by gather are in task_result
                failed_nodes[node.task_id] = str(task_result)
            elif node.state == NodeState.CANCELLED_DUE_TO_UPSTREAM:
                failed_nodes[node.task_id] = "Cancelled due to upstream failure."
        
        is_success = len(failed_nodes) == 0
        
        if is_success:
            logger.info("\n=== Pipeline executed successfully ===")
        else:
            logger.error(f"\n=== Pipeline interrupted: {len(failed_nodes)} node(s) failed/cancelled ===")
            
        self._export_trace(dag)

        return EngineResult(
            is_success=is_success,
            final_state=self.state,
            failed_tasks=failed_nodes
        )
