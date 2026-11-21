"""arXiv 检索：标准库实现 Atom XML 解析。"""

import html
import re
import ssl
import urllib.parse
import urllib.request
from typing import Dict, List

from .models import Paper

API = "https://export.arxiv.org/api/query"


def _ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_atom(xml: str) -> List[Paper]:
    """把 arXiv Atom XML 解析成 Paper 列表。纯字符串处理，无 lxml 依赖。"""
    papers: List[Paper] = []
    for entry in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        idm = re.search(r"<id>http://arxiv.org/abs/([^<]+)</id>", entry)
        if not idm:
            continue
        tim = re.search(r"<title>(.*?)</title>", entry, re.S)
        sim = re.search(r"<summary>(.*?)</summary>", entry, re.S)
        dim = re.search(r"<published>([^<]+)</published>", entry)
        authors = re.findall(r"<name>([^<]+)</name>", entry)
        arxiv_id = idm.group(1).strip()
        papers.append(Paper(
            arxiv_id=arxiv_id,
            identifier="arXiv:" + arxiv_id,
            title=_clean(tim.group(1)) if tim else "",
            abstract=_clean(sim.group(1)) if sim else "",
            published=dim.group(1)[:10] if dim else "",
            year=dim.group(1)[:4] if dim else "",
            authors=authors,
            source="arXiv preprint",
        ))
    return papers


def search(
    query: str,
    max_results: int = 5,
    sort: str = "submittedDate",
    timeout: int = 40,
) -> List[Paper]:
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": sort,
        "sortOrder": "descending",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "research-pipeline/0.1"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        xml = resp.read().decode("utf-8", "ignore")
    return parse_atom(xml)


def get_by_ids(ids: List[str], timeout: int = 40) -> List[Paper]:
    url = API + "?" + urllib.parse.urlencode({"id_list": ",".join(ids), "max_results": len(ids)})
    req = urllib.request.Request(url, headers={"User-Agent": "research-pipeline/0.1"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        xml = resp.read().decode("utf-8", "ignore")
    return parse_atom(xml)
