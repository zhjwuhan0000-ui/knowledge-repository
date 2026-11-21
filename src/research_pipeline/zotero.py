"""Zotero MCP 客户端：通过 Streamable HTTP 直连 Zotero 插件内置服务器。

仅用标准库。支持会话管理、SSE/JSON 双格式响应、工具发现与语义化封装。
"""

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .logger import get_logger


class ZoteroError(RuntimeError):
    """Zotero MCP 调用异常。"""


class ZoteroClient:
    def __init__(self, url: str, timeout: int = 60, verbose: bool = False):
        self.url = url
        self.timeout = timeout
        self.log = get_logger("zotero", verbose)
        self._session_id: Optional[str] = None
        self._req_id = 0
        self._ready = False

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _post(self, payload: Dict[str, Any], expect: bool = True) -> Optional[Dict]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        self.log.debug(f"POST {self.url} <- {str(payload)[:300]}")
        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self._session_id = sid
                raw = resp.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:300]
            raise ZoteroError(f"HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise ZoteroError(
                f"无法连接 {self.url}: {e.reason}。请确认 Zotero 正在运行、"
                "插件 MCP 服务器已启用（默认端口 23120）。"
            ) from e
        if not expect or not raw.strip():
            return None
        return self._parse(raw)

    @staticmethod
    def _parse(raw: str) -> Dict:
        raw = raw.strip()
        if raw.startswith("{"):
            return json.loads(raw)
        result = None
        for line in raw.splitlines():
            if line.strip().startswith("data:"):
                data = line.strip()[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    obj = json.loads(data)
                    if isinstance(obj, dict) and ("result" in obj or "error" in obj):
                        result = obj
                except json.JSONDecodeError:
                    continue
        if result is None:
            raise ZoteroError("无法解析 MCP 响应: " + raw[:300])
        return result

    def connect(self) -> None:
        if self._ready:
            return
        resp = self._post({
            "jsonrpc": "2.0", "id": self._next_id(), "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "research-pipeline", "version": "0.1.0"},
            },
        })
        if resp and "error" in resp:
            raise ZoteroError(f"initialize 失败: {resp['error']}")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}, expect=False)
        self._ready = True

    def list_tools(self) -> List[Dict]:
        self.connect()
        resp = self._post({"jsonrpc": "2.0", "id": self._next_id(), "method": "tools/list", "params": {}})
        if resp and "error" in resp:
            raise ZoteroError(f"tools/list 失败: {resp['error']}")
        return (resp or {}).get("result", {}).get("tools", [])

    def call(self, name: str, args: Optional[Dict[str, Any]] = None) -> Any:
        self.connect()
        resp = self._post({
            "jsonrpc": "2.0", "id": self._next_id(), "method": "tools/call",
            "params": {"name": name, "arguments": args or {}},
        })
        if not resp:
            return None
        if "error" in resp:
            raise ZoteroError(f"调用 {name} 失败: {resp['error']}")
        result = resp.get("result", {})
        if result.get("isError"):
            texts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
            raise ZoteroError(f"{name} 返回错误: {' '.join(texts)[:300]}")
        if "structuredContent" in result:
            return result["structuredContent"]
        texts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
        joined = "\n".join(texts).strip()
        if not joined:
            return result
        try:
            return json.loads(joined)
        except json.JSONDecodeError:
            return joined

    # 语义化封装
    def get_collections(self) -> Any:
        return self.call("get_collections", {"mode": "complete"})

    def get_collection_items(self, key: str) -> Any:
        return self.call("get_collection_items", {"collectionKey": key})

    def create_collection(self, name: str, parent: Optional[str] = None) -> Any:
        args: Dict[str, Any] = {"name": name}
        if parent:
            args["parentCollection"] = parent
        return self.call("create_collection", args)

    def search_library(self, query: str, **kwargs: Any) -> Any:
        return self.call("search_library", {"query": query, **kwargs})

    def add_by_identifier(
        self,
        identifiers: List[str],
        collection_key: Optional[str] = None,
        save_attachments: bool = False,
        skip_existing: bool = True,
        title_duplicates: str = "flag",
        dry_run: bool = False,
    ) -> Any:
        args: Dict[str, Any] = {
            "identifiers": identifiers,
            "saveAttachments": save_attachments,
            "skipExisting": skip_existing,
            "titleDuplicates": title_duplicates,
            "fileExisting": False,
        }
        if collection_key:
            args["collectionKey"] = collection_key
        if dry_run:
            args["dryRun"] = True
        return self.call("add_by_identifier", args)
