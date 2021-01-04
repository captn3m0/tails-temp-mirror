import logging
import subprocess
from typing import List

logger = logging.getLogger(__name__)

def run(cmd: List, *args, **kwargs) -> subprocess.CompletedProcess:
    cmd = [str(s) for s in cmd]
    logger.debug(f"Executing command {' '.join(cmd)}")
    return subprocess.run(cmd, *args, **kwargs)


def check_call(cmd: List, *args, **kwargs):
    cmd = [str(s) for s in cmd]
    logger.debug(f"Executing command {' '.join(cmd)}")
    subprocess.check_call(cmd, *args, **kwargs)


def check_output(cmd: List, *args, **kwargs) -> str:
    cmd = [str(s) for s in cmd]
    logger.debug(f"Executing command {' '.join(cmd)}")
    return subprocess.check_output(cmd, text=True, *args, **kwargs)
