from __future__ import annotations

import logging

from core.config import AppConfig


def setup_logging(config: AppConfig) -> None:
    config.log_file_path.parent.mkdir(parents=True, exist_ok=True)

    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    formatter = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    logging.basicConfig(
        level=log_level,
        format=formatter,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(config.log_file_path, encoding="utf-8"),
        ],
        force=True,
    )

    logging.getLogger("urllib3").setLevel(logging.WARNING)

