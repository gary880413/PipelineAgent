import pytest
import asyncio
import json
from pipeline_agent.schemas.schema import DAGPlan, TaskNode, NodeState, Runtime
from pipeline_agent.engine import AsyncPipelineEngine
from pipeline_agent.tools.tools import registry, tool

# ==========================================
# 🧪 Mock Tools for Testing
# ==========================================
call_counts = {"mock_success": 0}

@pytest.fixture(autouse=True)
def reset_mocks():
    """每次測試前重置計數器"""
    call_counts["mock_success"] = 0
    yield

@tool(category="test", runtime=Runtime.LOCAL_CPU, description="Mock Success")
async def mock_success_tool(val: str) -> str:
    call_counts["mock_success"] += 1
    return f"Processed: {val}"

@tool(category="test", runtime=Runtime.LOCAL_CPU, description="Mock Fail")
async def mock_fail_tool(val: str) -> str:
    raise ValueError("Intentional failure for testing")

# ==========================================
# 🧪 Test Cases
# ==========================================

@pytest.mark.asyncio
async def test_exactly_once_checkpointing(tmp_path):
    """
    測試目標：驗證快照機制能成功攔截重複執行，並將檔案寫入正確的 Hash 資料夾。
    """
    # 1. 初始化引擎，並將 Checkpoint 目錄指向 pytest 提供的隔離暫存區
    engine = AsyncPipelineEngine()
    engine.checkpoint_manager.base_dir = str(tmp_path / ".checkpoints")
    
    # 模擬一個經過時間與 SHA 計算的 Plan ID
    plan_id = "20260320_120000_a1b2c3d4"
    
    node = TaskNode(
        task_id="step_1",
        tool_name="mock_success_tool",
        runtime=Runtime.LOCAL_CPU.value,
        tool_inputs_json=json.dumps({"val": "hello"})
    )
    plan = DAGPlan(plan_id=plan_id, goal="test", nodes=[node])

    # --- 第一回合：正常執行 ---
    result1 = await engine.run(plan)
    assert result1.is_success == True
    assert call_counts["mock_success"] == 1
    assert result1.final_state["step_1"] == "Processed: hello"

    # 驗證資料夾是否如期建立
    expected_file = tmp_path / ".checkpoints" / plan_id / "state.json"
    assert expected_file.exists()

    # --- 第二回合：模擬 Agent 發生中斷後重新提交相同的 DAG ---
    node.state = NodeState.PENDING # 重置節點狀態，模擬新進來的藍圖
    plan2 = DAGPlan(plan_id=plan_id, goal="test", nodes=[node])
    
    result2 = await engine.run(plan2)
    assert result2.is_success == True
    
    # 🚨 核心斷言：即便跑了第二次，底層的 Tool 呼叫次數必須仍為 1！
    assert call_counts["mock_success"] == 1
    # 且結果必須能從快照中正確還原
    assert result2.final_state["step_1"] == "Processed: hello"


@pytest.mark.asyncio
async def test_safe_halting(tmp_path):
    """
    測試目標：驗證 A -> B -> C，當 B 失敗時，C 會被安全標記為 CANCELLED，且引擎不崩潰。
    """
    engine = AsyncPipelineEngine()
    engine.checkpoint_manager.base_dir = str(tmp_path / ".checkpoints")
    
    plan_id = "20260320_120000_f9e8d7c6"
    
    node_a = TaskNode(
        task_id="node_a", tool_name="mock_success_tool", 
        runtime=Runtime.LOCAL_CPU.value, tool_inputs_json='{"val": "A"}', depends_on=[]
    )
    # B 依賴 A，並會拋出錯誤
    node_b = TaskNode(
        task_id="node_b", tool_name="mock_fail_tool", 
        runtime=Runtime.LOCAL_CPU.value, tool_inputs_json='{"val": "${node_a.output}"}', depends_on=["node_a"]
    )
    # C 依賴 B
    node_c = TaskNode(
        task_id="node_c", tool_name="mock_success_tool", 
        runtime=Runtime.LOCAL_CPU.value, tool_inputs_json='{"val": "${node_b.output}"}', depends_on=["node_b"]
    )
    
    plan = DAGPlan(plan_id=plan_id, goal="test_halt", nodes=[node_a, node_b, node_c])
    
    result = await engine.run(plan)
    
    # 1. 整個 Pipeline 必須是失敗的
    assert result.is_success == False
    
    # 2. 🚨 核心斷言：狀態機的演變是否符合預期
    assert node_a.state == NodeState.SUCCESS
    assert node_b.state == NodeState.FAILED
    assert node_c.state == NodeState.CANCELLED_DUE_TO_UPSTREAM
    
    # 3. 確保 node_c 從未被執行
    assert call_counts["mock_success"] == 1 # 只有 node_a 被執行