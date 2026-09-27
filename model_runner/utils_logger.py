import os
from datetime import datetime

# =========================
# Paths
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "model_log.txt")

os.makedirs(LOG_DIR, exist_ok=True)


# =========================
# Logger Function
# =========================

def write_log(level, message):
    """
    Writes a log message to logs/model_log.txt
    Example:
    [2026-05-30 15:20:11] [INFO] Service started
    """

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_line = f"[{now}] [{level}] {message}\n"

    with open(LOG_FILE, "a", encoding="utf-8") as file:
        file.write(log_line)

    print(log_line.strip())