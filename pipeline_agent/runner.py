"""
Agentic Runner — Orchestration layer for PipelineAgent.

This module sits ABOVE both Planner and Engine, owning the plan → execute → replan
self-healing loop. It strictly preserves the architectural contract that:
  - Planner only generates DAGs (cloud brain).
  - Engine only executes DAGs (edge worker).
  - Engine never calls back into Planner.

The healing loop is an *orchestration concern*, not an *execution concern*,
and therefore lives here — not inside the Engine.

編排層：擁有「規劃 → 執行 → 重新規劃」的自我修復迴圈。
嚴格遵守架構契約：Planner 只產 DAG，Engine 只執行 DAG，
Engine 永遠不會反向呼叫 Planner。
"""

from typing import Optional

from pipeline_agent.planner.planner import PipelinePlanner
from pipeline_agent.engine.engine import AsyncPipelineEngine
from pipeline_agent.schemas.schema import EngineResult
from pipeline_agent.utils.logger import setup_logger

logger = setup_logger("pipeline_agent.runner")


class AgenticRunner:
    """
    Coordinates a PipelinePlanner and an AsyncPipelineEngine to provide
    self-healing agentic execution.
    
    協調 PipelinePlanner 與 AsyncPipelineEngine，提供自我修復的 Agentic 執行能力。
    """

    def __init__(self, planner: PipelinePlanner, engine: AsyncPipelineEngine):
        self.planner = planner
        self.engine = engine

    async def run(self, query: str, max_retries: int = 3) -> EngineResult:
        """
        Execute the full agentic loop: plan → run → on failure, replan & retry.
        
        執行完整的 Agentic 迴圈：規劃 → 執行 → 若失敗則重新規劃並重試。
        
        Args:
            query: The user's original task description.
            max_retries: Maximum number of attempts (including the initial run).
        
        Returns:
            EngineResult: The final execution result after all attempts.
        """
        current_plan = await self.planner.plan(query)

        result: Optional[EngineResult] = None
        for attempt in range(1, max_retries + 1):
            logger.info(f"🔄 [AgenticRunner] Attempt {attempt}/{max_retries}")

            result = await self.engine.run(current_plan)

            if result.is_success:
                logger.info(f"✅ [AgenticRunner] Task completed on attempt {attempt}")
                return result

            logger.warning(
                f"⚠️ [AgenticRunner] Attempt {attempt} failed — "
                f"{len(result.failed_tasks)} node(s) failed/cancelled"
            )

            if attempt < max_retries:
                logger.info("🚨 [AgenticRunner] Triggering dynamic re-planning (Self-Healing)...")
                current_plan = await self.planner.replan(
                    original_goal=query,
                    current_state=result.final_state,
                    failed_nodes=result.failed_tasks,
                )

        logger.error(f"❌ [AgenticRunner] All {max_retries} attempts exhausted")
        return result
