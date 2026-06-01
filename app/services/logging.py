import json
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("deepalpha")


def log_event(event: str, **fields: object) -> None:
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, ensure_ascii=False, default=str))
