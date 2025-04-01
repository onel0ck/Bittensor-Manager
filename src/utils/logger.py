import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger(name: str, log_file: str, level=logging.INFO):

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if name != 'registration_manager':
        main_handler = RotatingFileHandler(
            'logs/bittensor_manager.log',
            maxBytes=10*1024*1024,
            backupCount=5
        )
        main_handler.setFormatter(formatter)
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.addHandler(main_handler)
    else:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.WARNING)
    logger.addHandler(console_handler)

    return logger
