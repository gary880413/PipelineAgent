import asyncio
import re
from typing import Dict, Any, Optional
import json
import inspect # 🌟 新增引入 inspect

from pipeline_agent.schemas.schema import DAGPlan, TaskNode, EngineResult, Runtime
from pipeline_agent.tools.tools import registry
from pipeline_agent.exceptions import DependencyResolutionError, ToolExecutionError

from pipeline_agent.utils.logger import setup_logger
logger = setup_logger("pipeline_agent.planner")

class AsyncPipelineEngine:
    def __init__(self, resource_limits: Optional[Dict[str, int]] = None):
        self.state: Dict[str, Any] = {}
        self.events: Dict[str, asyncio.Event] = {}
        
        # 預設配置
        default_limits = {
            Runtime.LOCAL_CPU.value: 10,
            Runtime.LOCAL_GPU.value: 1,
            Runtime.CLOUD_API.value: 5
        }
        
        # 若使用者有傳入配置，則覆蓋預設值
        if resource_limits:
            default_limits.update(resource_limits)
            
        # 根據最終配置建立 Semaphore
        self.resource_locks = {
            k: asyncio.Semaphore(v) for k, v in default_limits.items()
        }

    def _resolve_inputs(self, inputs: dict, state: dict) -> dict:
        """
        將輸入參數中的 ${task_id.output} 替換為真實狀態值。
        支援單一變數替換 (保留原始型別) 與字串插值 (多變數組合)。
        """
        resolved = {}
        for k, v in inputs.items():
            if isinstance(v, str):
                # 情況 A：整個字串就是一個變數 (例如 "${step_1.output}")，這要保留原本的型別 (可能是 Dict/List)
                full_match = re.fullmatch(r'\$\{([^}]+)\.output\}', v)
                if full_match:
                    task_id = full_match.group(1)
                    if task_id not in state:
                        raise DependencyResolutionError(f"Dependency output for {task_id} not found in state.")
                    resolved[k] = state[task_id]
                    continue

                # 情況 B：字串插值 (例如 "NVDA: ${nvda.output}, TSMC: ${tsmc.output}")
                def replacer(match):
                    task_id = match.group(1)
                    if task_id not in state:
                        raise DependencyResolutionError(f"Dependency output for {task_id} not found in state.")
                    return str(state[task_id])
                
                # 將字串裡所有符合 ${xxx.output} 的部分全部替換掉
                resolved_str = re.sub(r'\$\{([^}]+)\.output\}', replacer, v)
                resolved[k] = resolved_str
            
            elif isinstance(v, dict):
                # 遞迴處理巢狀字典
                resolved[k] = self._resolve_inputs(v, state)
            elif isinstance(v, list):
                # 處理陣列
                resolved[k] = [self._resolve_inputs({"temp": item}, state)["temp"] for item in v]
            else:
                resolved[k] = v
                
        return resolved

    async def _execute_node(self, node: TaskNode):
        logger.info(f"[{node.task_id}] ⏳ 等待前置任務: {node.depends_on}")
        
        for dep in node.depends_on:
            await self.events[dep].wait()
            if isinstance(self.state.get(dep), Exception):
                logger.error(f"[{node.task_id}] ❌ 由於前置任務 '{dep}' 失敗，取消執行。")
                self.state[node.task_id] = Exception(f"Dependency {dep} failed.")
                self.events[node.task_id].set()
                return

        # 🌟 進入對應的資源池排隊
        lock = self.resource_locks.get(node.runtime, asyncio.Semaphore(1))
        logger.info(f"[{node.task_id}] 🚥 進入 [{node.runtime.upper()}] 資源池排隊中...")

        # 🌟 只有搶到該資源池的 Ticket (Semaphore) 才能往下執行
        async with lock:
            logger.info(f"[{node.task_id}] 🚀 取得 [{node.runtime.upper()}] 執行權！開始運算...")
            try:
                raw_inputs = json.loads(node.tool_inputs_json)
                resolved_inputs = self._resolve_inputs(raw_inputs, self.state)
                
                tool_info = registry._tools.get(node.tool_name)
                if not tool_info:
                    raise ToolExecutionError(f"找不到工具: {node.tool_name}")
                    
                func = tool_info["callable"]
                safe_log_inputs = {k: (str(v)[:50] + "..." if isinstance(v, str) and len(str(v)) > 50 else v) for k, v in resolved_inputs.items()}
                logger.info(f"[{node.task_id}] 呼叫 '{node.tool_name}' 參數: {safe_log_inputs}")
                
                # 智慧判斷同步/非同步
                if inspect.iscoroutinefunction(func):
                    result = await func(**resolved_inputs)
                else:
                    result = await asyncio.to_thread(func, **resolved_inputs)
                
                self.state[node.task_id] = result
                logger.info(f"[{node.task_id}] ✅ 任務完成，釋放 [{node.runtime.upper()}] 資源！")
                
            except Exception as e:
                logger.error(f"[{node.task_id}] ❌ 執行失敗: {str(e)}")
                self.state[node.task_id] = e
                
            finally:
                self.events[node.task_id].set()

    async def run(self, dag: DAGPlan) -> tuple[bool, Dict[str, Any], Dict[str, str]]:
        logger.info(f"\n=== 啟動 Pipeline Engine (Plan: {dag.plan_id}) ===\n")
        
        for node in dag.nodes:
            self.events[node.task_id] = asyncio.Event()

        tasks = [asyncio.create_task(self._execute_node(node)) for node in dag.nodes]
        await asyncio.gather(*tasks)
        
        # 🌟 災情盤點修正：只檢查「這次的 DAG 藍圖」裡面的節點是否有報錯
        failed_nodes = {}
        for node in dag.nodes:
            result = self.state.get(node.task_id)
            if isinstance(result, Exception):
                failed_nodes[node.task_id] = str(result)
        
        is_success = len(failed_nodes) == 0
        
        if is_success:
            logger.info("\n=== Pipeline 完美執行完畢 ===")
        else:
            logger.error(f"\n=== Pipeline 中斷：偵測到 {len(failed_nodes)} 個節點失敗 ===")
            
        return EngineResult(
            is_success=is_success,
            final_state=self.state,
            failed_tasks=failed_nodes
        )