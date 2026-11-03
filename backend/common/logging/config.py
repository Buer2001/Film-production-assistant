import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from backend.common.logging.context import request_id

logger = logging.getLogger('film')
FIELDS = ('operation', 'duration_ms', 'status', 'method', 'path', 'error_type', 'trace',
          'project_id', 'script_id', 'revision', 'scene_number', 'scene_index', 'field_name',
          'value_length', 'scene_count', 'error_count', 'provider', 'model', 'input_chars',
          'error_types', 'validation_errors', 'tool_call_count', 'operation_count')


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {'time': datetime.now(timezone.utc).isoformat(), 'level': record.levelname,
                   'event': record.getMessage(), 'request_id': request_id.get()}
        payload.update({field: getattr(record, field) for field in FIELDS if hasattr(record, field)})
        return json.dumps(payload, ensure_ascii=False)


def configure_logging():
    root = Path(__file__).resolve().parents[3]
    directory = Path(os.getenv('LOG_DIR', 'logs'))
    if not directory.is_absolute():
        directory = root / directory
    directory.mkdir(parents=True, exist_ok=True)
    # 测试会反复创建应用；只替换自己的 Handler，保留测试捕获器和外部配置。
    for handler in list(logger.handlers):
        if getattr(handler, '_film_managed', False):
            logger.removeHandler(handler)
            handler.close()
    file = RotatingFileHandler(directory / 'app.jsonl', maxBytes=5 * 1024 * 1024,
                               backupCount=3, encoding='utf-8')
    for handler in (file, logging.StreamHandler()):
        handler._film_managed = True
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return directory
