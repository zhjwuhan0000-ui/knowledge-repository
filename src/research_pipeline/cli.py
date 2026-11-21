"""命令行入口：research-pipeline / rp。

子命令：
  doctor  环境自检（Python 版本、Zotero 连接）
  init    生成配置示例
  search  检索 arXiv
  import  按标识符导入 Zotero
  notes   从论文数据 JSON 生成 Obsidian 笔记
  run     端到端流水线（检索→导入→笔记）
"""

import argparse
import json
import os
import sys
from typing import List, Optional

from . import __version__
from .arxiv import search as arxiv_search
from .config import load_config, write_example
from .logger import get_logger
from .models import Paper
from .notes import write_notes
from .pipeline import find_or_create_collection, import_papers, run_pipeline
from .zotero import ZoteroClient, ZoteroError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="research-pipeline",
        description="文献检索 → Zotero 导入 → Obsidian 笔记（独立运行，无需 WorkBuddy）",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--config", help="配置文件路径")
    p.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("doctor", help="环境自检")

    pi = sub.add_parser("init", help="生成配置示例文件")
    pi.add_argument("path", nargs="?", default="research-pipeline.json")

    ps = sub.add_parser("search", help="检索 arXiv")
    ps.add_argument("query", help='检索式，如 \'all:"small object detection"\'')
    ps.add_argument("--max", type=int, default=5)
    ps.add_argument("--sort", default="submittedDate")
    ps.add_argument("--out", help="结果保存为 JSON")

    pim = sub.add_parser("import", help="导入标识符到 Zotero")
    pim.add_argument("identifiers", nargs="+", help="arXiv:2304.00464 或 DOI")
    pim.add_argument("--collection", help="目标分类名（默认用配置里的）")
    pim.add_argument("--parent", help="父分类名（可选）")
    pim.add_argument("--attachments", action="store_true", help="尝试抓 PDF（默认关闭）")
    pim.add_argument("--dry-run", action="store_true")

    pn = sub.add_parser("notes", help="从论文 JSON 生成 Obsidian 笔记")
    pn.add_argument("input", help="论文数据 JSON（Paper 字段的数组或 {topic:[...]}）")
    pn.add_argument("--out", help="输出目录（默认用配置里的）")
    pn.add_argument("--template", help="模板文件（内置 11 节模板为默认）")
    pn.add_argument("--overwrite", action="store_true")

    pr = sub.add_parser("run", help="端到端流水线")
    pr.add_argument("--query", help="单个检索式")
    pr.add_argument("--topics", help="主题 JSON：{\"子目录\": [\"检索式\", ...]}")
    pr.add_argument("--collection", help="目标 Zotero 分类名")
    pr.add_argument("--max", type=int, default=5, help="每个检索式取几篇")
    pr.add_argument("--dry-run", action="store_true")

    return p


def cmd_doctor(args, cfg) -> int:
    print(f"Python: {sys.version.split()[0]}")
    print(f"配置文件: {cfg.to_dict()}")
    print(f"Zotero MCP: {cfg.zotero_mcp_url}")
    client = ZoteroClient(cfg.zotero_mcp_url, cfg.request_timeout, args.verbose)
    try:
        tools = client.list_tools()
        print(f"连接成功，可用工具 {len(tools)} 个: {', '.join(t.get('name', '') for t in tools)}")
        return 0
    except ZoteroError as e:
        print(f"连接失败: {e}", file=sys.stderr)
        return 1


def cmd_search(args, cfg) -> int:
    papers = arxiv_search(args.query, args.max, args.sort, cfg.request_timeout)
    data = [p.to_dict() for p in papers]
    out = json.dumps(data, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"保存 {len(papers)} 篇到 {args.out}", file=sys.stderr)
    else:
        print(out)
    return 0


def cmd_import(args, cfg) -> int:
    client = ZoteroClient(cfg.zotero_mcp_url, cfg.request_timeout, args.verbose)
    coll = args.collection or cfg.default_collection
    key = None
    if coll and not args.dry_run:
        key = find_or_create_collection(client, coll)
        print(f"分类「{coll}」key={key}", file=sys.stderr)
    result = import_papers(
        client, args.identifiers, key,
        save_attachments=args.attachments or cfg.save_attachments,
        batch_size=cfg.batch_size, dry_run=args.dry_run,
    )
    print(result.summary())
    print(json.dumps(result.to_dict() if hasattr(result, "to_dict") else {
        "succeeded": result.succeeded, "skipped": result.skipped,
        "duplicates": result.duplicates, "failed": result.failed,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_notes(args, cfg) -> int:
    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)
    groups = {"": data} if isinstance(data, list) else data
    tpl = None
    if args.template:
        with open(args.template, encoding="utf-8") as f:
            tpl = f.read()
    total = []
    for topic, items in groups.items():
        papers = [Paper.from_dict(d) for d in items]
        out_dir = args.out or cfg.note_output_dir
        if not out_dir:
            print("错误：请用 --out 或在配置里设置 note_output_dir", file=sys.stderr)
            return 1
        if topic:
            out_dir = os.path.join(out_dir, topic)
        total += write_notes(papers, out_dir, tpl, overwrite=args.overwrite)
    print(f"生成 {len(total)} 篇笔记")
    for path in total:
        print("  " + path)
    return 0


def cmd_run(args, cfg) -> int:
    topics = None
    if args.topics:
        with open(args.topics, encoding="utf-8") as f:
            topics = json.load(f)
    if not topics and not args.query:
        print("错误：请提供 --query 或 --topics", file=sys.stderr)
        return 1
    report = run_pipeline(
        cfg, args.query or "", max_results=args.max,
        collection_name=args.collection, topics=topics,
        dry_run=args.dry_run, verbose=args.verbose,
    )
    print(json.dumps({
        "papers": len(report["papers"]),
        "import": report["import"].summary() if report["import"] else None,
        "notes": len(report["notes"]),
        "note_files": report["notes"],
    }, ensure_ascii=False, indent=2))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0

    if args.cmd == "init":
        write_example(args.path)
        print(f"已生成配置示例: {args.path}")
        return 0

    try:
        cfg = load_config(args.config)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"配置错误: {e}", file=sys.stderr)
        return 2

    handlers = {
        "doctor": cmd_doctor, "search": cmd_search, "import": cmd_import,
        "notes": cmd_notes, "run": cmd_run,
    }
    return handlers[args.cmd](args, cfg)


if __name__ == "__main__":
    sys.exit(main())
