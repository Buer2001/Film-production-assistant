# 配置受管日志处理器和 JSON 白名单字段，支持轮转文件及控制台输出。
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


# 把标准日志和白名单诊断字段序列化为一行 JSON。
class JsonFormatter(logging.Formatter):
    # 把日志 record 转成 JSON 文本，仅包含基础信息、请求 ID 和允许的扩展字段。
    def format(self, record):
        payload = {'time': datetime.now(timezone.utc).isoformat(), 'level': record.levelname,
                   'event': record.getMessage(), 'request_id': request_id.get()}
        payload.update({field: getattr(record, field) for field in FIELDS if hasattr(record, field)})
        return json.dumps(payload, ensure_ascii=False)


# 按 LOG_DIR 创建目录并安装轮转文件和控制台处理器，返回日志目录；重复调用只替换本模块的处理器。
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
