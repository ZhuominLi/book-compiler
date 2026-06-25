"""Detect chapter heading pattern and body start — heuristic + optional LLM judge."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .llm import complete, has_llm

MIN_CHAPTER_CHARS = 600
PART_MARKER = re.compile(r"^第[一二三四五六七八九十]+部分", re.MULTILINE)
_TOC_NOISE = re.compile(r"[|｜]\s*\d+\s*$")
_CN = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "两": 2}
_UNITS = {"十": 10, "百": 100, "千": 1000}

SYSTEM_JUDGE = """你是 OCR 书籍 txt 的分章判断器。根据样例行判断章节标题格式。
只输出一行 JSON，无其它文字：
{"unit":"章|回|篇|节","number_style":"arabic|chinese","line_pattern":"standalone|inline","confidence":0.0-1.0}
standalone=标题独占一行；inline=第X回/章与标题同一行。"""


@dataclass
class HeadingMatch:
    line: int
    num: int
    title: str
    raw: str


@dataclass
class SplitProfile:
    pattern_id: str
    unit: str
    number_style: str
    body_start_line: int
    chapters_found: int
    confidence: float
    sample_title: str = ""

    def label(self) -> str:
        return f"第{{n}}{self.unit}（{'阿拉伯数字' if self.number_style == 'arabic' else '中文数字'}）"


def _body_start_hint(text: str) -> int:
    """Skip front TOC — prefer 第X部分 marker after early pages."""
    lines = text.splitlines()
    part_lines = [i for i, ln in enumerate(lines) if PART_MARKER.match(ln.strip())]
    for pl in part_lines:
        if pl > 300:
            return pl
    if len(part_lines) > 1:
        return part_lines[-1]
    return part_lines[0] if part_lines else 0


def _is_noise_heading(stripped: str) -> bool:
    if _TOC_NOISE.search(stripped):
        return True
    if re.search(r"[，,].{4,}[|｜]", stripped):
        return True
    return False


def cn_to_int(text: str) -> int:
    text = text.strip()
    if text.isdigit():
        return int(text)
    section = 0
    number = 0
    for ch in text:
        if ch in _CN:
            number = _CN[ch]
        elif ch in _UNITS:
            section += (number or 1) * _UNITS[ch]
            number = 0
    return section + number


def _parse_num(raw: str, style: str) -> int:
    return int(raw) if style == "arabic" else cn_to_int(raw)


def _title_after(lines: list[str], i: int, heading_re: re.Pattern) -> str:
    for j in range(i + 1, min(i + 4, len(lines))):
        t = lines[j].strip()
        if not t or t.startswith("---") or len(t) > 120:
            continue
        if heading_re.match(t):
            break
        if re.match(r"^(诗曰|却说|话说|卷[一二三四])", t):
            return ""
        return t[:80]
    return ""


def _build_patterns() -> list[tuple[str, str, str, re.Pattern]]:
    """(pattern_id, unit, number_style, regex)"""
    arabic = r"\d{1,3}"
    cn = r"[一二三四五六七八九十百千零〇两]+"
    out: list[tuple[str, str, str, re.Pattern]] = []

    for unit in ("章", "回", "篇", "节", "夜"):
        out.append(
            (
                f"{unit}_arabic_standalone",
                unit,
                "arabic",
                re.compile(rf"^第\s*({arabic})\s*{unit}\s*$"),
            )
        )
        out.append(
            (
                f"{unit}_arabic_inline",
                unit,
                "arabic",
                re.compile(rf"^第\s*({arabic})\s*{unit}\s*(.+)$"),
            )
        )
        out.append(
            (
                f"{unit}_cn_standalone",
                unit,
                "cn",
                re.compile(rf"^第({cn}){unit}\s*$"),
            )
        )
        out.append(
            (
                f"{unit}_cn_inline",
                unit,
                "cn",
                re.compile(rf"^第({cn}){unit}\s*(.+)$"),
            )
        )
    return out


PATTERNS = _build_patterns()


def _scan_matches(text: str, pattern_id: str, unit: str, style: str, rx: re.Pattern) -> list[HeadingMatch]:
    lines = text.splitlines()
    hits: list[HeadingMatch] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) > 100:
            continue
        if _is_noise_heading(stripped):
            continue
        m = rx.match(stripped)
        if not m:
            continue
        num = _parse_num(m.group(1), "arabic" if style == "arabic" else "cn")
        if num <= 0 or num > 999:
            continue
        title = (m.group(2).strip() if m.lastindex and m.lastindex >= 2 and m.group(2) else "") or _title_after(
            lines, i, rx
        )
        hits.append(HeadingMatch(i, num, title, stripped))
    return hits


def _chunk_len(lines: list[str], start: int, end: int) -> int:
    return len("".join(lines[start:end]))


def _greedy_chain(lines: list[str], hits: list[HeadingMatch], min_line: int = 0) -> list[HeadingMatch]:
    """From each 第一X starter, greedily pick nearest valid next chapter."""
    if not hits:
        return []
    by_num: dict[int, list[HeadingMatch]] = {}
    for h in hits:
        if h.line >= min_line:
            by_num.setdefault(h.num, []).append(h)

    starters = sorted(by_num.get(1, []), key=lambda h: h.line)
    best: list[HeadingMatch] = []

    for starter in starters:
        chain = [starter]
        cursor = starter.line
        expected = 2
        while expected in by_num or expected + 1 in by_num:
            cands = [h for h in by_num.get(expected, []) if h.line > cursor]
            if not cands and expected + 1 in by_num:
                expected += 1
                continue
            if not cands:
                break
            cands.sort(key=lambda h: h.line)
            picked = next(
                (c for c in cands if _chunk_len(lines, cursor, c.line) >= MIN_CHAPTER_CHARS),
                None,
            )
            if not picked:
                break
            chain.append(picked)
            cursor = picked.line
            expected = picked.num + 1
        if len(chain) > len(best):
            best = chain
    return best


def _pick_body_chain(
    lines: list[str], hits: list[HeadingMatch], min_line: int = 0
) -> tuple[list[HeadingMatch], int]:
    if not hits:
        return [], 0
    chain = _greedy_chain(lines, hits, min_line=min_line)
    if not chain:
        return [], 0
    return chain, chain[0].line


def _score_pattern(text: str, pattern_id: str, unit: str, style: str, rx: re.Pattern) -> SplitProfile | None:
    hits = _scan_matches(text, pattern_id, unit, style, rx)
    if len(hits) < 2:
        return None
    lines = text.splitlines()
    min_line = _body_start_hint(text)
    chain, body_start = _pick_body_chain(lines, hits, min_line=min_line)
    if len(chain) < 2:
        return None
    valid = 0
    for idx, h in enumerate(chain):
        end = chain[idx + 1].line if idx + 1 < len(chain) else len(lines)
        if _chunk_len(lines, h.line, end) >= MIN_CHAPTER_CHARS:
            valid += 1
    if valid < 2:
        return None
    confidence = min(0.98, 0.45 + valid * 0.02 + len(chain) * 0.005)
    return SplitProfile(
        pattern_id=pattern_id,
        unit=unit,
        number_style="arabic" if style == "arabic" else "chinese",
        body_start_line=body_start,
        chapters_found=len(chain),
        confidence=confidence,
        sample_title=chain[0].title or chain[0].raw,
    )


def detect_profile_heuristic(text: str) -> SplitProfile | None:
    best: SplitProfile | None = None
    for pattern_id, unit, style, rx in PATTERNS:
        prof = _score_pattern(text, pattern_id, unit, style, rx)
        if prof and (best is None or prof.chapters_found > best.chapters_found or (
            prof.chapters_found == best.chapters_found and prof.confidence > best.confidence
        )):
            best = prof
    return best


def _sample_lines(text: str, n: int = 40) -> str:
    lines = text.splitlines()
    if len(lines) <= n * 3:
        return "\n".join(f"{i+1}|{ln}" for i, ln in enumerate(lines[:200]))
    head = [f"{i+1}|{lines[i]}" for i in range(min(80, len(lines)))]
    mids = []
    for frac in (0.15, 0.35, 0.55):
        start = int(len(lines) * frac)
        mids.extend(f"{start+i+1}|{lines[start+i]}" for i in range(8) if start + i < len(lines))
    return "\n".join(head + ["..."] + mids)


def judge_profile_llm(text: str, heuristic: SplitProfile | None) -> SplitProfile | None:
    if not has_llm():
        return heuristic
    hint = ""
    if heuristic:
        hint = f"启发式判断：{heuristic.label()}，约 {heuristic.chapters_found} 章，正文起 L{heuristic.body_start_line + 1}"
    user = f"{hint}\n\n样例行：\n{_sample_lines(text)}\n\n输出 JSON。"
    try:
        raw = complete(SYSTEM_JUDGE, user).strip()
        m = re.search(r"\{[^{}]+\}", raw)
        if not m:
            return heuristic
        data = json.loads(m.group())
        unit = data.get("unit", "章")
        style = data.get("number_style", "chinese")
        # re-run heuristic restricted to matching patterns
        filtered = [
            p for p in PATTERNS
            if p[1] == unit and (p[2] == "arabic") == (style == "arabic")
        ]
        if not filtered and heuristic:
            return heuristic
        best = None
        for pattern_id, u, s, rx in filtered or PATTERNS:
            prof = _score_pattern(text, pattern_id, u, s, rx)
            if prof and (best is None or prof.chapters_found > best.chapters_found):
                best = prof
        if best:
            best.confidence = max(best.confidence, float(data.get("confidence", 0.7)))
        return best or heuristic
    except Exception:
        return heuristic


def resolve_split_profile(text: str, *, use_llm: bool = True) -> SplitProfile:
    h = detect_profile_heuristic(text)
    if use_llm and has_llm():
        j = judge_profile_llm(text, h)
        if j:
            return j
    if h:
        return h
    raise RuntimeError(
        "未能识别章节标题。支持：第X章 / 第X回 / 第X篇 / 第X夜（阿拉伯或中文数字，独占一行或与标题同行）；EPUB 将尝试按目录分章"
    )


def find_chapters(text: str, profile: SplitProfile) -> list[tuple[int, int, str]]:
    """Return [(line_start, chapter_num, title), ...] for splitting."""
    pattern = next(p for p in PATTERNS if p[0] == profile.pattern_id)
    hits = _scan_matches(text, *pattern)
    lines = text.splitlines()
    min_line = max(_body_start_hint(text), profile.body_start_line)
    chain, _ = _pick_body_chain(lines, hits, min_line=min_line)
    return [(h.line, h.num, h.title) for h in chain]
