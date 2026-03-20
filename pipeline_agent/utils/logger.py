# File path: pipeline_agent/utils/logger.py

import logging
import sys

def setup_logger(name: str) -> logging.Logger:
    """
    Create a unified Logger format for PipelineAgent.
    """
    logger = logging.getLogger(name)
    
    # Avoid adding handlers multiple times if logger already has handlers
    if not logger.handlers:
        # Default level set to INFO
        logger.setLevel(logging.INFO)
        
        # Create a handler for outputting to the console
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # Set log format
        # Example: [2026-03-19 11:45:00] [PipelineAgent] [INFO] 🧠 Building DAG blueprint...
        formatter = logging.Formatter(
            '%(asctime)s | [%(name)s] | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        
        logger.addHandler(console_handler)
        
        # Prevent log messages from being propagated to the root logger
        logger.propagate = False
        
    return logger

# Provide a global method for users to adjust the log level of the entire package in their main.py
def set_global_log_level(level: int):
    """
    Allow developers to adjust the global log level of PipelineAgent (e.g., logging.DEBUG, logging.WARNING)
    """
    for logger_name in logging.root.manager.loggerDict:
        if logger_name.startswith('pipeline_agent'):
            logging.getLogger(logger_name).setLevel(level)
            for handler in logging.getLogger(logger_name).handlers:
                handler.setLevel(level)