import os
import sys
from core.config import settings

BUFFER_SUBDIR = "discovery_buffer"
TARGET_BUFFER_SIZE = getattr(settings, "STREAM_BUFFER_SIZE", 10)
RETENTION_DAYS = 3
import base64
HISTORY_FILENAME = "stream_history.json"
LEGACY_HISTORY_FILENAME = base64.b64decode("d2F2ZV9oaXN0b3J5Lmpzb24=").decode("utf-8")
SAVED_DISCOVERIES_DIRNAME = "Saved_Discoveries"


def safe_print(*args, **kwargs):
    """Безопасный вывод в консоль с защитой от UnicodeEncodeError (cp1251 на Windows)."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        try:
            sep = kwargs.get("sep", " ")
            msg = sep.join(str(a) for a in args)
            safe_msg = msg.encode("ascii", errors="replace").decode("ascii")
            print(safe_msg)
        except Exception:
            pass
    except Exception:
        pass
