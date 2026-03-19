import pytest
import asyncio
import json
import time
from pipeline_agent import (
    tool, 
    Runtime, 
    DefaultCategory, 
    AsyncPipelineEngine
)
from pipeline_agent.schemas.schema import DAGPlan, TaskNode

# ==========================================
# 1. 準備測試專用的 Dummy Tools
# ==========================================

@tool(category=DefaultCategory.TEXT_PROCESSING, runtime=Runtime.LOCAL_CPU, description="測試用 CPU 任務")
async def dummy_cpu_echo(text: str) -> str:
    await asyncio.sleep(0.1)  # 模擬輕量耗時
    return f"CPU_ECHO:{text}"

@tool(category=DefaultCategory.TEXT_PROCESSING, runtime=Runtime.LOCAL_GPU, description="測試用 GPU 任務")
async def dummy_gpu_heavy(text: str) -> str:
    await asyncio.sleep(0.5)  # 模擬推論耗時
    return f"GPU_RESULT:{text}"

@tool(category=DefaultCategory.TEXT_PROCESSING, runtime=Runtime.LOCAL_CPU, description="測試用報錯任務")
async def dummy_fail_task() -> str:
    raise ValueError("System Crash Simulation")


# ==========================================
# 2. 測試案例撰寫
# ==========================================

@pytest.mark.asyncio
async def test_happy_path_variable_resolution():
    """測試一：驗證 DAG 依賴等待與變數注入 (${task_id.output}) 是否正確"""
    
    # 手動構造一張 A -> B 的 DAG
    plan = DAGPlan(
        plan_id="test_plan_01",
        goal="Test variables",
        nodes=[
            TaskNode(
                task_id="step_1",
                tool_name="dummy_cpu_echo",
                runtime=Runtime.LOCAL_CPU,
                tool_inputs_json=json.dumps({"text": "Hello"}),
                depends_on=[]
            ),
            TaskNode(
                task_id="step_2",
                tool_name="dummy_gpu_heavy",
                runtime=Runtime.LOCAL_GPU,
                # 驗證變數替換是否成功
                tool_inputs_json=json.dumps({"text": "${step_1.output} World"}),
                depends_on=["step_1"]
            )
        ]
    )

    engine = AsyncPipelineEngine()
    is_success, state, failed = await engine.run(plan)

    assert is_success is True
    assert len(failed) == 0
    # 驗證 step_1 正確執行
    assert state["step_1"] == "CPU_ECHO:Hello"
    # 驗證 step_2 成功等待 step_1，並拿到替換後的字串
    assert state["step_2"] == "GPU_RESULT:CPU_ECHO:Hello World"


@pytest.mark.asyncio
async def test_resource_locks_concurrency():
    """測試二：驗證 Runtime Semaphore 是否真能限制 GPU 併發並允許 CPU 並行"""
    
    # 構造 3 個 CPU 任務與 3 個 GPU 任務，彼此無依賴 (平行觸發)
    nodes = []
    for i in range(3):
        nodes.append(TaskNode(
            task_id=f"cpu_{i}", tool_name="dummy_cpu_echo", runtime=Runtime.LOCAL_CPU,
            tool_inputs_json=json.dumps({"text": "test"}), depends_on=[]
        ))
        nodes.append(TaskNode(
            task_id=f"gpu_{i}", tool_name="dummy_gpu_heavy", runtime=Runtime.LOCAL_GPU,
            tool_inputs_json=json.dumps({"text": "test"}), depends_on=[]
        ))
        
    plan = DAGPlan(plan_id="test_plan_02", goal="Test Concurrency", nodes=nodes)
    
    # 嚴格設定：CPU 允許 10 個併發，GPU 僅允許 1 個
    engine = AsyncPipelineEngine(resource_limits={
        Runtime.LOCAL_CPU.value: 10,
        Runtime.LOCAL_GPU.value: 1
    })

    start_time = time.time()
    await engine.run(plan)
    elapsed = time.time() - start_time

    # 理論耗時計算：
    # 3 個 CPU (耗時 0.1s) 平行跑 -> 總耗時約 0.1s
    # 3 個 GPU (耗時 0.5s) 必須排隊跑 -> 總耗時約 1.5s
    # 兩組平行觸發，所以總耗時應落在 1.5s ~ 1.7s 之間。
    # 如果 Semaphore 沒生效，GPU 也平行跑，總耗時會只有 0.5s！
    assert elapsed >= 1.5, "GPU 併發鎖未生效，任務被平行執行了！"


@pytest.mark.asyncio
async def test_error_propagation_and_halting():
    """測試三：驗證單點故障時，依賴它的下游任務會被取消，但獨立任務仍會完成"""
    
    plan = DAGPlan(
        plan_id="test_plan_03",
        goal="Test Error Handling",
        nodes=[
            TaskNode( # 這個會報錯
                task_id="step_fail", tool_name="dummy_fail_task", runtime=Runtime.LOCAL_CPU,
                tool_inputs_json="{}", depends_on=[]
            ),
            TaskNode( # 依賴報錯節點，應該被取消 (連帶報錯)
                task_id="step_dependent", tool_name="dummy_cpu_echo", runtime=Runtime.LOCAL_CPU,
                tool_inputs_json=json.dumps({"text": "Never run"}), depends_on=["step_fail"]
            ),
            TaskNode( # 完全獨立的節點，應該要成功
                task_id="step_independent", tool_name="dummy_cpu_echo", runtime=Runtime.LOCAL_CPU,
                tool_inputs_json=json.dumps({"text": "I am alive"}), depends_on=[]
            )
        ]
    )

    engine = AsyncPipelineEngine()
    is_success, state, failed = await engine.run(plan)

    assert is_success is False
    assert len(failed) == 2 # step_fail 和 step_dependent 都算失敗
    assert isinstance(state["step_fail"], ValueError)
    assert isinstance(state["step_dependent"], Exception)
    assert "Dependency step_fail failed" in str(state["step_dependent"])
    
    # 證明引擎的非同步隔離性：即便別人崩潰，獨立分支依然能完成任務
    assert state["step_independent"] == "CPU_ECHO:I am alive"