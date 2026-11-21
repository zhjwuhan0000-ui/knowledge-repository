"""数据模型：用 dataclass 承载论文/分类/配置，避免外部依赖。"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class Paper:
    """一篇论文的结构化数据。"""

    title: str = ""
    authors: List[str] = field(default_factory=list)
    year: str = ""
    source: str = ""
    zotero_key: str = ""
    collection: str = ""
    keywords: List[str] = field(default_factory=list)
    research_question: str = ""
    method: str = ""
    data: str = ""
    main_findings: str = ""
    innovation: str = ""
    limitations: str = ""
    # 检索/导入用
    arxiv_id: str = ""
    identifier: str = ""
    abstract: str = ""
    published: str = ""

    @property
    def arxiv_identifier(self) -> str:
        if self.identifier:
            return self.identifier
        if self.arxiv_id:
            return "arXiv:" + self.arxiv_id
        return ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "Paper":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Collection:
    """Zotero 分类。"""

    key: str
    name: str
    parent: str = ""


@dataclass
class ImportResult:
    """一次导入的结果统计。"""

    succeeded: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    duplicates: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"成功 {len(self.succeeded)} / 跳过 {len(self.skipped)} / "
            f"疑似重复 {len(self.duplicates)} / 失败 {len(self.failed)}"
        )

    def to_dict(self) -> Dict:
        return asdict(self)
