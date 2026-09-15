import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from mailbucket import __version__
from mailbucket.config import RunConfig


def write_metadata(
    path: Path, config: RunConfig, stats: dict, buckets: dict, status: str = "complete"
) -> None:
    data = {
        "application": "MailBucket",
        "version": __version__,
        "created_at": datetime.now().astimezone().isoformat(),
        "status": status,
        **asdict(config),
        "statistics": stats,
        "bucket_directories": buckets,
        "naive_dates": "UTC",
        "numbering_minimum_width": 4,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
