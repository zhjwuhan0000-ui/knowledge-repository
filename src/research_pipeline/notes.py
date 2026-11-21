"""笔记生成：按 11 节模板渲染 Obsidian Markdown。"""

import os
import re
from typing import Dict, List, Optional

from .models import Paper

DEFAULT_TEMPLATE = """---
title: "{{title}}"
authors: [{{authors}}]
year: {{year}}
source: "{{source}}"
zotero_key: "@{{zotero_key}}"
collection: "{{collection}}"
keywords: [{{keywords}}]
status: "processed"
created: "{{created}}"
---

# {{title}}

## 1. 基本信息
- 标题：{{title}}
- 作者：{{authors}}
- 年份：{{year}}
- 来源：{{source}}
- Zotero条目：@{{zotero_key}}
- 所属文件夹：{{collection}}

## 2. 一句话总结
{{main_findings}}

## 3. 研究问题
{{research_question}}

## 4. 研究方法
{{method}}

## 5. 实验与数据
{{data}}

## 6. 核心发现
{{main_findings}}

## 7. 创新点
{{innovation}}

## 8. 局限性
{{limitations}}

## 9. 与当前课题的关系
{{relation}}

## 10. 可引用内容
> {{quote}}

## 11. 后续检索标签
{{keywords}}
"""

FIELD_MAP = {
    "title": "title", "authors": "authors", "year": "year", "source": "source",
    "zotero_key": "zotero_key", "collection": "collection", "keywords": "keywords",
    "research_question": "research_question", "method": "method", "data": "data",
    "main_findings": "main_findings", "innovation": "innovation",
    "limitations": "limitations", "relation": "relation", "quote": "quote",
    "created": "created",
}

INVALID = r'[\\/:*?"<>|]'


def as_str(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(x) for x in value)
    return "" if value is None else str(value)


def render(paper: Paper, template: Optional[str] = None, created: str = "") -> str:
    tpl = template if template is not None else DEFAULT_TEMPLATE
    data = paper.to_dict()
    data.setdefault("relation", "待补充：请说明当前研究方向")
    data.setdefault("quote", "（摘抄原文中适合综述/开题/写作的句子）")
    data["created"] = created or data.get("created", "")
    out = tpl
    for ph, field in FIELD_MAP.items():
        out = out.replace("{{" + ph + "}}", as_str(data.get(field, "")))
    return out


def filename(paper: Paper) -> str:
    short = paper.title.split(":")[0].strip()
    short = re.sub(INVALID, "_", short)[:40]
    return f"{paper.year}-{short}.md" if paper.year else f"{short}.md"


def write_notes(
    papers: List[Paper],
    out_dir: str,
    template: Optional[str] = None,
    created: str = "",
    overwrite: bool = False,
) -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for paper in papers:
        path = os.path.join(out_dir, filename(paper))
        if os.path.exists(path) and not overwrite:
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(render(paper, template, created))
        written.append(path)
    return written
