from __future__ import annotations

import sqlite3
import warnings
from pathlib import Path

from langchain_core.load.load import Reviver

_ALLOWED_OBJECTS_WARNING = (
    "The default value of `allowed_objects` will change in a future version.*"
)

# langgraph-checkpoint 2.x constructs its module-level Reviver without exposing
# allowed_objects through SqliteSaver. Silence only that import-time warning,
# then replace the reviver with the same policy made explicit.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=_ALLOWED_OBJECTS_WARNING)
    from langgraph.checkpoint.serde import jsonplus as checkpoint_jsonplus
    from langgraph.checkpoint.sqlite import SqliteSaver

checkpoint_jsonplus.LC_REVIVER = Reviver(allowed_objects="core")


class CheckpointManager:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.saver = SqliteSaver(self.connection)
        self.saver.setup()

    def close(self) -> None:
        self.connection.close()
