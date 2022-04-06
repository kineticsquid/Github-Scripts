import logging
import sys

def get_logger():
    logger = logging.getLogger('My Logger')
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(threadName)s - %(message)s', "%H:%M:%S")
    ch.setFormatter(formatter)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger