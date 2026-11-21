"""配置管理：JSON 文件 + 环境变量覆盖，仅标准库。"""

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULTS: Dict[str, Any] = {
    "zotero_mcp_url": "http://127.0.0.1:23120/mcp",
    "obsidian_vault": "",
    "template_path": "",
    "note_output_dir": "",
    "default_collection": "",
    "save_attachments": False,
    "batch_size": 3,
    "request_timeout": 60,
}

ENV_MAP = {
    "ZOTERO_MCP_URL": "zotero_mcp_url",
    "OBSIDIAN_VAULT": "obsidian_vault",
    "NOTE_OUTPUT_DIR": "note_output_dir",
    "DEFAULT_COLLECTION": "default_collection",
}


@dataclass
class Config:
    zotero_mcp_url: str = DEFAULTS["zotero_mcp_url"]
    obsidian_vault: str = ""
    template_path: str = ""
    note_output_dir: str = ""
    default_collection: str = ""
    save_attachments: bool = False
    batch_size: int = 3
    request_timeout: int = 60

    def validate(self) -> None:
        problems = []
        if not self.zotero_mcp_url:
            problems.append("zotero_mcp_url 不能为空")
        if self.batch_size < 1:
            problems.append("batch_size 必须 >= 1")
        if problems:
            raise ValueError("配置错误: " + "; ".join(problems))

    def to_dict(self) -> Dict:
        return asdict(self)


def find_config_file(explicit: Optional[str] = None) -> Optional[Path]:
    """按优先级找配置文件：显式 > 当前目录 > 用户目录。"""
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates += [
        Path.cwd() / "research-pipeline.json",
        Path.home() / ".research-pipeline.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def load_config(explicit: Optional[str] = None) -> Config:
    data = dict(DEFAULTS)
    path = find_config_file(explicit)
    if path:
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            data.update({k: v for k, v in loaded.items() if not k.startswith("_")})

    # 环境变量覆盖（优先级最高）
    for env_key, field_name in ENV_MAP.items():
        if env_key in os.environ:
            data[field_name] = os.environ[env_key]

    known = set(Config.__dataclass_fields__)
    cfg = Config(**{k: v for k, v in data.items() if k in known})
    cfg.validate()
    return cfg


def write_example(path: str) -> None:
    """生成配置示例文件。"""
    example = dict(DEFAULTS)
    example["_comment"] = "改成你自己的值；也可用环境变量 ZOTERO_MCP_URL / OBSIDIAN_VAULT 等覆盖"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(example, f, ensure_ascii=False, indent=2)
