# 檔案路徑: pipeline_agent/utils/logger.py

import logging
import sys

def setup_logger(name: str) -> logging.Logger:
    """
    為 PipelineAgent 建立統一格式的 Logger。
    """
    logger = logging.getLogger(name)
    
    # 如果 logger 已經有 handler，避免重複加入導致印兩次
    if not logger.handlers:
        # 預設層級設為 INFO
        logger.setLevel(logging.INFO)
        
        # 建立輸出到終端機 (Console) 的 Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # 設定日誌格式 (Format)
        # 例如: [2026-03-19 11:45:00] [PipelineAgent] [INFO] 🧠 構建 DAG 藍圖中...
        formatter = logging.Formatter(
            '%(asctime)s | [%(name)s] | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        
        logger.addHandler(console_handler)
        
        # 避免將日誌往上傳遞給 root logger (防止被別的套件印出來)
        logger.propagate = False
        
    return logger

# 提供一個全域的方法讓使用者可以在他們的 main.py 中調整整個套件的日誌層級
def set_global_log_level(level: int):
    """
    允許開發者調整 PipelineAgent 的全域日誌層級 (例如 logging.DEBUG, logging.WARNING)
    """
    for logger_name in logging.root.manager.loggerDict:
        if logger_name.startswith('pipeline_agent'):
            logging.getLogger(logger_name).setLevel(level)
            for handler in logging.getLogger(logger_name).handlers:
                handler.setLevel(level)