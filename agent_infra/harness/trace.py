"""O 层：traceId 关联的结构化 JSONL 事件流（唯一事实源，日志是投影）。

# ponytail: 字段刻意对齐 OpenTelemetry（traceId/spanId/parentSpanId），
# 不引 OTLP；接 Jaeger/云观测时换 exporter 即可。
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


class Tracer:
    def __init__(self, runs_root: Path, trace_id: str) -> None:
        self.trace_id = trace_id
        self._dir = Path(runs_root) / trace_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "trace.jsonl"

    def emit(self, event: str, *, node_id: str | None = None,
             parent_span_id: str | None = None, **payload: Any) -> str:
        span_id = uuid.uuid4().hex[:16]
        record = {
            "ts": time.time(),
            "trace_id": self.trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "event": event,
            "node_id": node_id,
            "payload": payload,
        }
        with self._file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return span_id
