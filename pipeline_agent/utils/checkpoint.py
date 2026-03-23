import os
import json
from typing import Any, Optional, Dict
import logging

logger = logging.getLogger("pipeline_agent.checkpoint")

class CheckpointManager:
    """
    負責 DAG 執行期間的狀態持久化，確保 Exactly-Once 執行語意。
    目前實作為 Local File System (JSON based)。
    """
    def __init__(self, base_dir: str = ".checkpoints"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def _get_filepath(self, plan_id: str) -> str:
        return os.path.join(self.base_dir, f"{plan_id}_checkpoint.json")

    def save_node_output(self, plan_id: str, node_id: str, output: Any) -> None:
        """將成功的節點輸出寫入硬碟快照"""
        filepath = self._get_filepath(plan_id)
        data = self.load_all(plan_id)
        data[node_id] = output
        
        # 使用 atomic write 思維，確保寫入時斷電不會損毀檔案
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug(f"Saved checkpoint for node '{node_id}' in plan '{plan_id}'.")

    def get_node_output(self, plan_id: str, node_id: str) -> Optional[Any]:
        """讀取指定節點的快照"""
        data = self.load_all(plan_id)
        return data.get(node_id)

    def load_all(self, plan_id: str) -> Dict[str, Any]:
        """載入該計畫的所有成功快照"""
        filepath = self._get_filepath(plan_id)
        if not os.path.exists(filepath):
            return {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"Checkpoint file {filepath} is corrupted. Returning empty state.")
            return {}