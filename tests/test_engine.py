import pytest
import asyncio
import json
import time
from pipeline_agent import (
    engine,
    tool, 
    Runtime, 
    DefaultCategory, 
    AsyncPipelineEngine
)
from pipeline_agent.schemas.schema import DAGPlan, TaskNode

# ==========================================
# 1. Prepare Dummy Tools for Testing
# ==========================================

@tool(category=DefaultCategory.TEXT_PROCESSING, runtime=Runtime.LOCAL_CPU, description="Test CPU task")
async def dummy_cpu_echo(text: str) -> str:
    await asyncio.sleep(0.1)  # Simulate lightweight workload
    return f"CPU_ECHO:{text}"

@tool(category=DefaultCategory.TEXT_PROCESSING, runtime=Runtime.LOCAL_GPU, description="Test GPU task")
async def dummy_gpu_heavy(text: str) -> str:
    await asyncio.sleep(0.5)  # Simulate inference workload
    return f"GPU_RESULT:{text}"

@tool(category=DefaultCategory.TEXT_PROCESSING, runtime=Runtime.LOCAL_CPU, description="Test error task")
async def dummy_fail_task() -> str:
    raise ValueError("System Crash Simulation")


# ==========================================
# 2. Test Cases
# ==========================================

@pytest.mark.asyncio
async def test_happy_path_variable_resolution():
    """Test 1: Verify DAG dependency waiting and variable injection (${task_id.output}) correctness"""
    
    # Manually construct a DAG: A -> B
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
                # Verify variable replacement
                tool_inputs_json=json.dumps({"text": "${step_1.output} World"}),
                depends_on=["step_1"]
            )
        ]
    )

    engine = AsyncPipelineEngine()

    result = await engine.run(plan)

    assert result.is_success is True
    assert len(result.failed_tasks) == 0
    # Verify step_1 executed correctly
    assert result.final_state["step_1"] == "CPU_ECHO:Hello"
    # Verify step_2 waited for step_1 and got the replaced string
    assert result.final_state["step_2"] == "GPU_RESULT:CPU_ECHO:Hello World"


@pytest.mark.asyncio
async def test_resource_locks_concurrency():
    """Test 2: Verify Runtime Semaphore can limit GPU concurrency and allow CPU parallelism"""
    
    # Construct 3 CPU tasks and 3 GPU tasks, all independent (triggered in parallel)
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
    
    # Strict setting: CPU allows 10 concurrent, GPU allows only 1
    engine = AsyncPipelineEngine(resource_limits={
        Runtime.LOCAL_CPU.value: 10,
        Runtime.LOCAL_GPU.value: 1
    })

    start_time = time.time()
    await engine.run(plan)
    elapsed = time.time() - start_time

    # Theoretical time calculation:
    # 3 CPU tasks (0.1s each) run in parallel -> total ~0.1s
    # 3 GPU tasks (0.5s each) must queue -> total ~1.5s
    # Both groups triggered in parallel, so total time should be between 1.5s ~ 1.7s.
    # If Semaphore fails, GPU tasks also run in parallel, total time would be only 0.5s!
    assert elapsed >= 1.5, "GPU concurrency lock failed, tasks ran in parallel!"


@pytest.mark.asyncio
async def test_error_propagation_and_halting():
    """Test 3: Verify that when a single point fails, downstream dependent tasks are cancelled, but independent tasks still complete"""
    
    plan = DAGPlan(
        plan_id="test_plan_03",
        goal="Test Error Handling",
        nodes=[
            TaskNode( # This one will raise an error
                task_id="step_fail", tool_name="dummy_fail_task", runtime=Runtime.LOCAL_CPU,
                tool_inputs_json="{}", depends_on=[]
            ),
            TaskNode( # Depends on the failed node, should be cancelled (also failed)
                task_id="step_dependent", tool_name="dummy_cpu_echo", runtime=Runtime.LOCAL_CPU,
                tool_inputs_json=json.dumps({"text": "Never run"}), depends_on=["step_fail"]
            ),
            TaskNode( # Completely independent node, should succeed
                task_id="step_independent", tool_name="dummy_cpu_echo", runtime=Runtime.LOCAL_CPU,
                tool_inputs_json=json.dumps({"text": "I am alive"}), depends_on=[]
            )
        ]
    )

    engine = AsyncPipelineEngine()
    result = await engine.run(plan)

    assert result.is_success is False
    assert len(result.failed_tasks) == 2 # step_fail and step_dependent both failed
    
    # Note: When the engine fails, the error object is placed in failed_tasks, not in final_state
    assert "System Crash Simulation" in str(result.failed_tasks["step_fail"])
    assert "Dependency step_fail failed" in str(result.failed_tasks["step_dependent"])
    
    # Prove engine's async isolation: even if others crash, independent branches can still complete, successful results are in final_state
    assert result.final_state["step_independent"] == "CPU_ECHO:I am alive"