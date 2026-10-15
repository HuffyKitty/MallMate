"""将 Markdown 知识离线整理为父子片段。

该模块不调用大模型、不访问数据库。输出的 JSONL 可人工抽查，后续再由独立导入程序
写入 PostgreSQL 和 ChromaDB。父片段保留完整小节上下文，子片段用于精确检索。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE = PROJECT_ROOT / "knowledge" / "policies"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "rag" / "knowledge_chunks.jsonl"
CHUNKER_VERSION = "mallmate-small-to-big-v1"


@dataclass(frozen=True)
class ChunkingConfig:
    """字符长度是初始切片界限，不等同于模型 Token 数。"""

    parent_target_chars: int = 1400
    parent_max_chars: int = 1800
    child_target_chars: int = 340
    child_max_chars: int = 500


@dataclass(frozen=True)
class MarkdownBlock:
    text: str
    title_path: tuple[str, ...]
    kind: str = "text"


@dataclass(frozen=True)
class MarkdownSection:
    title_path: tuple[str, ...]
    blocks: tuple[MarkdownBlock, ...]


@dataclass(frozen=True)
class ChunkRecord:
    """可序列化的父/子片段记录；后续数据库导入可直接复用字段。"""

    chunk_id: str
    document_id: str
    document_title: str
    version: str
    category: str
    status: str
    level: str
    parent_chunk_id: str | None
    ordinal: int
    title_path: list[str]
    source_uri: str
    source_anchor: str
    content_hash: str
    chunker_version: str
    content: str
    embedding_text: str | None
    char_count: int


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """读取项目当前使用的简易 YAML Front Matter 字段，不引入 YAML 依赖。"""

    normalized = text.lstrip("\ufeff")
    lines = normalized.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, normalized

    closing = next(
        (index for index in range(1, len(lines)) if lines[index].strip() in {"---", "..."}),
        None,
    )
    if closing is None:
        return {}, normalized

    metadata: dict[str, str] = {}
    for line in lines[1:closing]:
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip().strip("\"'")
    return metadata, "\n".join(lines[closing + 1 :]).strip()


def _markdown_kind(text: str) -> str:
    lines = text.splitlines()
    if lines and all(line.lstrip().startswith("|") for line in lines):
        return "table"
    if lines and all(
        not line.strip()
        or re.match(r"^\s*(?:[-*+]\s+|\d+[.)、]\s+)", line)
        for line in lines
    ):
        return "list"
    if lines and lines[0].lstrip().startswith("```"):
        return "code"
    return "text"


def _parse_sections(body: str, document_title: str) -> list[MarkdownSection]:
    """按二级标题建立父级语义区，保留三级及更深标题作为子片段上下文。"""

    sections: list[MarkdownSection] = []
    current_heading = document_title
    current_blocks: list[MarkdownBlock] = []
    paragraph_lines: list[str] = []
    local_path: tuple[str, ...] = (document_title,)

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        value = "\n".join(paragraph_lines).strip()
        if value:
            current_blocks.append(
                MarkdownBlock(value, local_path, _markdown_kind(value))
            )
        paragraph_lines = []

    def flush_section() -> None:
        flush_paragraph()
        if current_blocks:
            section_heading = (
                MarkdownBlock(
                    f"## {current_heading}",
                    (document_title, current_heading),
                    "heading_h2",
                )
                if current_heading != document_title
                else None
            )
            section_blocks = ([section_heading] if section_heading else []) + list(current_blocks)
            sections.append(
                MarkdownSection(
                    title_path=(document_title, current_heading)
                    if current_heading != document_title
                    else (document_title,),
                    blocks=tuple(section_blocks),
                )
            )
        current_blocks.clear()

    for line in body.splitlines():
        if re.match(r"^#\s+", line):
            flush_paragraph()
            heading = re.sub(r"^#\s+", "", line).strip()
            if heading:
                document_title = heading
                if not current_blocks:
                    current_heading = document_title
                    local_path = (document_title,)
            continue

        h2 = re.match(r"^##\s+(.+?)\s*#*\s*$", line)
        if h2:
            flush_section()
            current_heading = h2.group(1).strip()
            local_path = (document_title, current_heading)
            continue

        subheading = re.match(r"^(#{3,6})\s+(.+?)\s*#*\s*$", line)
        if subheading:
            flush_paragraph()
            level = len(subheading.group(1))
            title = subheading.group(2).strip()
            local_path = (document_title, current_heading, title)
            current_blocks.append(
                MarkdownBlock(line.strip(), local_path, f"heading_h{level}")
            )
            continue

        if line.strip():
            paragraph_lines.append(line.rstrip())
        else:
            flush_paragraph()

    flush_section()
    return sections


_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?；;])")


def _split_text_block(text: str, max_chars: int) -> list[str]:
    """优先按列表项/句子切长段，只有单句仍超长时才按字符边界兜底。"""

    lines = text.splitlines()
    is_list = len(lines) > 1 and all(
        re.match(r"^\s*(?:[-*+]\s+|\d+[.)、]\s+)", line)
        for line in lines
    )
    pieces = [line.strip() for line in lines if line.strip()] if is_list else [text.strip()]
    result: list[str] = []

    for piece in pieces:
        if len(piece) <= max_chars:
            result.append(piece)
            continue

        sentences = [part.strip() for part in _SENTENCE_BOUNDARY.split(piece) if part.strip()]
        if len(sentences) <= 1:
            result.extend(
                piece[start : start + max_chars].strip()
                for start in range(0, len(piece), max_chars)
                if piece[start : start + max_chars].strip()
            )
            continue

        current = ""
        for sentence in sentences:
            if len(sentence) > max_chars:
                if current:
                    result.append(current)
                    current = ""
                result.extend(
                    sentence[start : start + max_chars].strip()
                    for start in range(0, len(sentence), max_chars)
                    if sentence[start : start + max_chars].strip()
                )
            elif current and len(current) + len(sentence) + 1 > max_chars:
                result.append(current)
                current = sentence
            else:
                if not current:
                    current = sentence
                else:
                    separator = " " if current[-1:].isascii() and sentence[:1].isascii() else ""
                    current = f"{current}{separator}{sentence}"
        if current:
            result.append(current)
    return result


def _split_table_block(text: str, max_chars: int) -> list[str]:
    """长表格按数据行分组，每组重复表头和分隔线。"""

    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if len(lines) <= 2 or len(text) <= max_chars:
        return [text]

    header = lines[:2]
    rows = lines[2:]
    groups: list[str] = []
    current = list(header)
    current_chars = sum(len(line) for line in current)
    for row in rows:
        if current_chars + len(row) > max_chars and len(current) > len(header):
            groups.append("\n".join(current))
            current = list(header)
            current_chars = sum(len(line) for line in current)
        current.append(row)
        current_chars += len(row)
    if len(current) > len(header):
        groups.append("\n".join(current))
    return groups or [text]


def _expand_blocks(blocks: Iterable[MarkdownBlock], max_chars: int) -> list[MarkdownBlock]:
    expanded: list[MarkdownBlock] = []
    for block in blocks:
        if len(block.text) <= max_chars:
            expanded.append(block)
            continue
        pieces = (
            _split_table_block(block.text, max_chars)
            if block.kind == "table"
            else _split_text_block(block.text, max_chars)
        )
        expanded.extend(MarkdownBlock(piece, block.title_path, block.kind) for piece in pieces)
    return expanded


def _pack_blocks(
    blocks: Iterable[MarkdownBlock],
    target_chars: int,
    max_chars: int,
    *,
    split_on_section_heading: bool = False,
) -> list[list[MarkdownBlock]]:
    groups: list[list[MarkdownBlock]] = []
    current: list[MarkdownBlock] = []
    current_size = 0
    for block in blocks:
        block_size = len(block.text)
        if (
            split_on_section_heading
            and block.kind == "heading_h2"
            and current
            and current_size >= min(target_chars, 200)
        ):
            groups.append(current)
            current = []
            current_size = 0
        if current and current_size + block_size + 2 > max_chars:
            groups.append(current)
            current = []
            current_size = 0
        current.append(block)
        current_size += block_size + (2 if len(current) > 1 else 0)
        if current_size >= target_chars:
            groups.append(current)
            current = []
            current_size = 0
    if current:
        groups.append(current)
    return groups


def _common_title_path(blocks: Iterable[MarkdownBlock]) -> tuple[str, ...]:
    paths = [block.title_path for block in blocks if block.title_path]
    if not paths:
        return ()
    common: list[str] = []
    for values in zip(*paths):
        if len(set(values)) != 1:
            break
        common.append(values[0])
    return tuple(common) or paths[0]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _make_id(
    document_id: str,
    version: str,
    level: str,
    ordinal: int,
    title_path: tuple[str, ...],
    content_hash: str,
) -> str:
    path_hash = _hash("/".join(title_path))[:8]
    return f"{document_id}:{version}:{level}:{ordinal:04d}:{path_hash}:{content_hash[:10]}"


def _anchor(title_path: tuple[str, ...]) -> str:
    return "#" + "-".join(
        re.sub(r"[^\w\u4e00-\u9fff]+", "-", part.lower()).strip("-")
        for part in title_path
    )


def chunk_markdown(
    text: str,
    *,
    source_uri: str,
    config: ChunkingConfig = ChunkingConfig(),
) -> list[ChunkRecord]:
    """生成父片段和子片段；每个子片段只对应一个父片段。"""

    metadata, body = _split_frontmatter(text)
    document_id = metadata.get("id") or Path(source_uri).stem
    document_title = metadata.get("title") or Path(source_uri).stem
    version = metadata.get("version", "unversioned")
    category = metadata.get("category", "general")
    status = metadata.get("status", "active")

    sections = _parse_sections(body, document_title)
    records: list[ChunkRecord] = []
    parent_ordinal = 0
    child_ordinal = 0

    all_blocks = [block for section in sections for block in section.blocks]
    parent_blocks = _pack_blocks(
        _expand_blocks(all_blocks, config.parent_max_chars),
        config.parent_target_chars,
        config.parent_max_chars,
    )
    for parent_group in parent_blocks:
        parent_content = "\n\n".join(block.text for block in parent_group).strip()
        if not parent_content:
            continue
        parent_path = _common_title_path(parent_group) or (document_title,)
        parent_hash = _hash(parent_content)
        parent_id = _make_id(
            document_id,
            version,
            "parent",
            parent_ordinal,
            parent_path,
            parent_hash,
        )
        records.append(
            ChunkRecord(
                chunk_id=parent_id,
                document_id=document_id,
                document_title=document_title,
                version=version,
                category=category,
                status=status,
                level="parent",
                parent_chunk_id=None,
                ordinal=parent_ordinal,
                title_path=list(parent_path),
                source_uri=source_uri,
                source_anchor=_anchor(parent_path),
                content_hash=parent_hash,
                chunker_version=CHUNKER_VERSION,
                content=parent_content,
                embedding_text=None,
                char_count=len(parent_content),
            )
        )

        child_blocks = _expand_blocks(parent_group, config.child_max_chars)
        for child_group in _pack_blocks(
            child_blocks,
            config.child_target_chars,
            config.child_max_chars,
            split_on_section_heading=True,
        ):
            child_content = "\n\n".join(block.text for block in child_group).strip()
            if not child_content:
                continue
            child_path = _common_title_path(child_group) or parent_path
            child_hash = _hash(child_content)
            child_id = _make_id(
                document_id,
                version,
                "child",
                child_ordinal,
                child_path,
                child_hash,
            )
            embedding_text = f"標題路徑：{' > '.join(child_path)}\n{child_content}"
            records.append(
                ChunkRecord(
                    chunk_id=child_id,
                    document_id=document_id,
                    document_title=document_title,
                    version=version,
                    category=category,
                    status=status,
                    level="child",
                    parent_chunk_id=parent_id,
                    ordinal=child_ordinal,
                    title_path=list(child_path),
                    source_uri=source_uri,
                    source_anchor=_anchor(child_path),
                    content_hash=child_hash,
                    chunker_version=CHUNKER_VERSION,
                    content=child_content,
                    embedding_text=embedding_text,
                    char_count=len(child_content),
                )
            )
            child_ordinal += 1
        parent_ordinal += 1

    return records


def _relative_uri(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.name


def chunk_files(
    source: Path,
    config: ChunkingConfig = ChunkingConfig(),
) -> tuple[list[ChunkRecord], list[dict[str, str]]]:
    files = [source] if source.is_file() else sorted(source.rglob("*.md"))
    all_records: list[ChunkRecord] = []
    errors: list[dict[str, str]] = []
    for path in files:
        try:
            document = path.read_text(encoding="utf-8")
            records = chunk_markdown(
                document,
                source_uri=_relative_uri(path),
                config=config,
            )
            if not records:
                errors.append({"source": _relative_uri(path), "error": "文档没有可切片正文"})
            all_records.extend(records)
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(
                {"source": _relative_uri(path), "error": f"{type(exc).__name__}: {exc}"}
            )
    return all_records, errors


def _write_jsonl(records: Iterable[ChunkRecord], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    temporary.replace(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="离线生成 MallMate Markdown 父子切片")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Markdown 文件或目录")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="JSONL 输出文件")
    parser.add_argument("--parent-target", type=int, default=1400, help="父片段目标字符数")
    parser.add_argument("--parent-max", type=int, default=1800, help="父片段最大字符数")
    parser.add_argument("--child-target", type=int, default=340, help="子片段目标字符数")
    parser.add_argument("--child-max", type=int, default=500, help="子片段最大字符数")
    parser.add_argument("--preview", action="store_true", help="只显示统计和前 3 个子片段，不写输出文件")
    args = parser.parse_args()

    if not args.source.exists():
        parser.error(f"知识源路径不存在：{args.source}")
    if not args.source.is_file() and not args.source.is_dir():
        parser.error("知识源必须是 Markdown 文件或目录")
    if min(args.parent_target, args.parent_max, args.child_target, args.child_max) <= 0:
        parser.error("切片长度必须大于 0")
    if args.parent_target > args.parent_max or args.child_target > args.child_max:
        parser.error("target 长度不能大于 max 长度")

    config = ChunkingConfig(
        parent_target_chars=args.parent_target,
        parent_max_chars=args.parent_max,
        child_target_chars=args.child_target,
        child_max_chars=args.child_max,
    )
    records, errors = chunk_files(args.source, config)
    parents = [record for record in records if record.level == "parent"]
    children = [record for record in records if record.level == "child"]
    summary = {
        "source": str(args.source),
        "documents": len({record.document_id for record in records}),
        "parent_chunks": len(parents),
        "child_chunks": len(children),
        "parent_chars": {
            "min": min((record.char_count for record in parents), default=0),
            "max": max((record.char_count for record in parents), default=0),
            "average": round(
                sum(record.char_count for record in parents) / max(len(parents), 1), 1
            ),
        },
        "child_chars": {
            "min": min((record.char_count for record in children), default=0),
            "max": max((record.char_count for record in children), default=0),
            "average": round(
                sum(record.char_count for record in children) / max(len(children), 1), 1
            ),
        },
        "errors": errors,
    }

    if args.preview:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        for record in children[:3]:
            print("\n--- SAMPLE CHILD ---")
            print(json.dumps(asdict(record), ensure_ascii=False, indent=2))
    else:
        _write_jsonl(records, args.output)
        summary["output"] = str(args.output)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
