import asyncio
import re
from typing import Dict, Any, Optional
import json
import inspect  # 🌟 Newly import inspect

from pipeline_agent.schemas.schema import DAGPlan, TaskNode, EngineResult, Runtime
from pipeline_agent.tools.tools import registry
from pipeline_agent.exceptions import DependencyResolutionError, ToolExecutionError

from pipeline_agent.utils.logger import setup_logger
logger = setup_logger("pipeline_agent.planner")

class AsyncPipelineEngine:
    def __init__(self, resource_limits: Optional[Dict[str, int]] = None):
        self.state: Dict[str, Any] = {}
        self.events: Dict[str, asyncio.Event] = {}
        
        # Default configuration
        default_limits = {
            Runtime.LOCAL_CPU.value: 10,
            Runtime.LOCAL_GPU.value: 1,
            Runtime.CLOUD_API.value: 5
        }
        
        # Override defaults if user provides configuration
        if resource_limits:
            default_limits.update(resource_limits)
            
        # Create Semaphore for each resource type based on final configuration
        self.resource_locks = {
            k: asyncio.Semaphore(v) for k, v in default_limits.items()
        }

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

    async def _execute_node(self, node: TaskNode):
        logger.info(f"[{node.task_id}] ⏳ Waiting for dependencies: {node.depends_on}")
        
        for dep in node.depends_on:
            await self.events[dep].wait()
            if isinstance(self.state.get(dep), Exception):
                logger.error(f"[{node.task_id}] ❌ Canceled execution due to failed dependency '{dep}'.")
                self.state[node.task_id] = Exception(f"Dependency {dep} failed.")
                self.events[node.task_id].set()
                return

        # 🌟 Queue for the corresponding resource pool
        lock = self.resource_locks.get(node.runtime, asyncio.Semaphore(1))
        logger.info(f"[{node.task_id}] 🚥 Queuing in [{node.runtime.upper()}] resource pool...")

        # 🌟 Only proceed if a ticket (Semaphore) for the resource pool is acquired
        async with lock:
            logger.info(f"[{node.task_id}] 🚀 Acquired [{node.runtime.upper()}] execution right! Starting computation...")
            try:
                raw_inputs = json.loads(node.tool_inputs_json)
                resolved_inputs = self._resolve_inputs(raw_inputs, self.state)
                
                tool_info = registry._tools.get(node.tool_name)
                if not tool_info:
                    raise ToolExecutionError(f"Tool not found: {node.tool_name}")
                    
                func = tool_info["callable"]
                safe_log_inputs = {k: (str(v)[:50] + "..." if isinstance(v, str) and len(str(v)) > 50 else v) for k, v in resolved_inputs.items()}
                logger.info(f"[{node.task_id}] Calling '{node.tool_name}' with params: {safe_log_inputs}")
                
                # Smartly determine sync/async
                if inspect.iscoroutinefunction(func):
                    result = await func(**resolved_inputs)
                else:
                    result = await asyncio.to_thread(func, **resolved_inputs)
                
                self.state[node.task_id] = result
                logger.info(f"[{node.task_id}] ✅ Task completed, releasing [{node.runtime.upper()}] resource!")
                
            except Exception as e:
                logger.error(f"[{node.task_id}] ❌ Execution failed: {str(e)}")
                self.state[node.task_id] = e
                
            finally:
                self.events[node.task_id].set()

    async def run(self, dag: DAGPlan) -> EngineResult: 
        logger.info(f"\n=== Starting Pipeline Engine (Plan: {dag.plan_id}) ===\n")
        
        for node in dag.nodes:
            self.events[node.task_id] = asyncio.Event()

        tasks = [asyncio.create_task(self._execute_node(node)) for node in dag.nodes]
        await asyncio.gather(*tasks)
        
        # 🌟 Only check for errors in nodes within this DAG plan
        failed_nodes = {}
        for node in dag.nodes:
            result = self.state.get(node.task_id)
            if isinstance(result, Exception):
                failed_nodes[node.task_id] = str(result)
        
        is_success = len(failed_nodes) == 0
        
        if is_success:
            logger.info("\n=== Pipeline executed successfully ===")
        else:
            logger.error(f"\n=== Pipeline interrupted: {len(failed_nodes)} node(s) failed ===")
            
        return EngineResult(
            is_success=is_success,
            final_state=self.state,
            failed_tasks=failed_nodes
        )