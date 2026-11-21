"""流水线编排：把检索、导入、笔记三步串起来。"""

import json
import os
from datetime import date
from typing import Any, Dict, List, Optional

from .arxiv import get_by_ids, search
from .config import Config
from .logger import get_logger
from .models import ImportResult, Paper
from .notes import write_notes
from .zotero import ZoteroClient


def _extract_collection_key(collections: Any, name: str) -> Optional[str]:
    """从 get_collections 返回值里按名字找 key，兼容多种结构。"""
    items = collections if isinstance(collections, list) else (
        collections.get("collections") or collections.get("items") or []
    )
    for c in items or []:
        if isinstance(c, dict) and (c.get("name") == name or c.get("title") == name):
            return c.get("key")
    return None


def find_or_create_collection(client: ZoteroClient, name: str, parent_key: Optional[str] = None) -> str:
    key = _extract_collection_key(client.get_collections(), name)
    if key:
        return key
    created = client.create_collection(name, parent=parent_key)
    if isinstance(created, dict):
        return created.get("key", "")
    return ""


def import_papers(
    client: ZoteroClient,
    identifiers: List[str],
    collection_key: Optional[str],
    save_attachments: bool = False,
    batch_size: int = 3,
    dry_run: bool = False,
) -> ImportResult:
    """按标识符分批导入（默认每批 ≤3 篇，稳妥）。"""
    result = ImportResult()
    for i in range(0, len(identifiers), batch_size):
        batch = identifiers[i:i + batch_size]
        try:
            resp = client.add_by_identifier(
                batch,
                collection_key=collection_key,
                save_attachments=save_attachments,
                dry_run=dry_run,
            )
            _accumulate_result(result, batch, resp)
        except Exception as e:  # noqa: BLE001 - 单批失败不中断后续
            result.failed.extend(batch)
            get_logger("pipeline").warning(f"批次导入失败: {e}")
    return result


def _accumulate_result(result: ImportResult, batch: List[str], resp: Any) -> None:
    """尽量从 MCP 返回里读出每篇的状态；解析不了就整批记为成功。"""
    if resp is None:
        result.succeeded.extend(batch)
        return
    if isinstance(resp, dict):
        for key, label in (("succeeded", "succeeded"), ("skipped", "skipped"),
                           ("duplicates", "duplicates"), ("failed", "failed")):
            vals = resp.get(key) or resp.get(label) or []
            if isinstance(vals, list):
                getattr(result, key).extend(str(v) for v in vals)
        if not any([result.succeeded, result.skipped, result.duplicates, result.failed]):
            result.succeeded.extend(batch)
    else:
        result.succeeded.extend(batch)


def load_template(path: Optional[str]) -> Optional[str]:
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def run_pipeline(
    cfg: Config,
    query: str,
    max_results: int = 5,
    collection_name: Optional[str] = None,
    topics: Optional[Dict[str, List[str]]] = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """端到端：检索 → 导入 Zotero → 生成 Obsidian 笔记。

    topics: 可选 {子目录名: [检索式,...]}，用于按主题建对称子目录。
    """
    log = get_logger("pipeline", verbose)
    report: Dict[str, Any] = {"papers": [], "import": None, "notes": []}

    client = ZoteroClient(cfg.zotero_mcp_url, cfg.request_timeout, verbose)
    collection_name = collection_name or cfg.default_collection

    def process_topic(topic: str, queries: List[str]) -> None:
        papers: List[Paper] = []
        for q in queries:
            log.info(f"检索: {q}")
            papers.extend(search(q, max_results=max_results, timeout=cfg.request_timeout))
        # 去重（按 arXiv ID）
        seen = set()
        papers = [p for p in papers if not (p.arxiv_id in seen or seen.add(p.arxiv_id))]
        log.info(f"主题「{topic}」检索到 {len(papers)} 篇")
        report["papers"].extend(p.to_dict() for p in papers)

        if not papers:
            return

        coll_key = None
        if not dry_run and collection_name:
            coll_key = find_or_create_collection(client, collection_name)
            log.info(f"Zotero 分类「{collection_name}」key={coll_key}")

        identifiers = [p.arxiv_identifier for p in papers if p.arxiv_identifier]
        imp = import_papers(
            client, identifiers, coll_key,
            save_attachments=cfg.save_attachments,
            batch_size=cfg.batch_size,
            dry_run=dry_run,
        )
        report["import"] = imp
        log.info("导入: " + imp.summary())

        if cfg.note_output_dir:
            out_dir = os.path.join(cfg.note_output_dir, topic) if topic else cfg.note_output_dir
            tpl = load_template(cfg.template_path)
            today = str(date.today())
            written = write_notes(papers, out_dir, tpl, today)
            report["notes"].extend(written)
            log.info(f"笔记写入 {len(written)} 篇 -> {out_dir}")

    if topics:
        for topic, queries in topics.items():
            process_topic(topic, queries)
    else:
        process_topic("", [query])

    return report
