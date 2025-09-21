import threading
from typing import Dict


class _Counter:
    def __init__(self):
        self._lock = threading.Lock()
        self._values: Dict[str, int] = {}

    def inc(self, name: str, amount: int = 1):
        with self._lock:
            self._values[name] = self._values.get(name, 0) + amount

    def render_prom(self) -> str:
        lines = []
        for k, v in sorted(self._values.items()):
            metric = k.replace('.', '_')
            lines.append(f"# TYPE {metric} counter")
            lines.append(f"{metric} {v}")
        return "\n".join(lines) + "\n"


COUNTERS = _Counter()

