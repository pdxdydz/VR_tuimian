#!/usr/bin/env python3
"""
北航计算机学院推免课程加权平均分核算（虚拟现实技术专业）

加权平均分 = Σ(课程成绩 × 课程学分) / Σ课程学分

默认读取：
  - 课程计算清单 PDF（虚拟现实技术专业页）
  - 本科生学业成绩表 PDF（PyMuPDF 文本提取）

用法:
  python calculate_tuimian_gpa.py
  python calculate_tuimian_gpa.py -o result.csv
  python calculate_tuimian_gpa.py --list path/to/清单.pdf --transcript path/to/成绩表.pdf
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Iterable, Optional

import fitz  # PyMuPDF

# ---------------------------------------------------------------------------
# 默认路径
# ---------------------------------------------------------------------------
DEFAULT_DOC_DIR = Path("/Users/pdxdydz/Desktop/Official Documents/北航推免")
DEFAULT_LIST_PDF = DEFAULT_DOC_DIR / (
    "北京航空航天大学计算机学院2024年推荐优秀应届本科毕业生"
    "免试攻读研究生课程计算清单.pdf"
)
DEFAULT_TRANSCRIPT_PDF = DEFAULT_DOC_DIR / "本科生学业成绩表（中文）.pdf"
DEFAULT_OUTPUT_CSV = Path(__file__).resolve().parent / "tuimian_gpa_result.csv"
VR_MAJOR_MARKER = "虚拟现实技术专业"

INTRO_COURSES = frozenset(
    {
        "计算机导论与伦理学",
        "走进软件",
        "仪器科学概览",
        "电子信息工程导论",
        "自动化科学与电气工程导论",
        "网络空间安全导论",
        "集成电路导论",
    }
)

# 虚拟现实技术专业推免课程清单（与学院 PDF 一致；PDF 解析作校验）
VR_CATALOG: dict[str, float] = {
    "工科数学分析（1）": 6.0,
    "工科高等代数": 6.0,
    "工科数学分析（2）": 6.0,
    "概率统计A": 3.0,
    "基础物理学（信息类）": 4.0,
    "工科大学物理（2）": 4.0,
    "程序设计基础": 2.0,
    "电子设计基础训练": 2.0,
    "离散数学（信息类）": 2.0,
    "数据结构与程序设计（信息类）": 3.0,
    "大英A1": 2.0,
    "大英A2": 2.0,
    "大英A3": 2.0,
    "大英B1": 2.0,
    "大英B2": 2.0,
    "大英B3": 2.0,
    "航空航天概论B": 1.5,
    "法律、科技与社会": 2.0,
    "虚拟现实技术基础": 1.0,
    "实时三维图形基础": 2.0,
    "离散数学（2）": 3.0,
    "计算机组成": 5.5,
    "操作系统": 4.5,
    "算法设计与分析": 2.0,
    "虚拟现实理论与算法": 2.0,
    "虚拟现实系统基础": 2.0,
    "虚拟现实人机交互": 2.0,
    "设计思维与创新": 2.0,
    "虚拟现实实验1": 1.0,
    "虚拟现实实验2": 1.0,
    "计算机网络": 2.0,
    "虚拟现实基础应用技术": 2.0,
    "计算机网络实验": 1.0,
    "计算机科学方法论": 2.0,
    **{name: 1.5 for name in INTRO_COURSES},
}

# 不计入专业选修候选的非专业课关键词
NON_ELECTIVE_KEYWORDS = (
    "体育",
    "军事",
    "心理健康",
    "素质教育",
    "形势与政策",
    "国家安全",
    "思想道德",
    "毛泽东",
    "习近平",
    "马克思主义",
    "中国近现代史",
    "社会实践",
    "音乐",
    "劳动",
    "启航",
    "岗位胜任",
    "科研课堂",
    "国际学术交流",
)

# ---------------------------------------------------------------------------
# 成绩与学期
# ---------------------------------------------------------------------------
GRADE_TO_SCORE = {
    "优秀": 95.0,
    "良好": 85.0,
    "中等": 75.0,
    "及格": 65.0,
    "不及格": 0.0,
}

SEMESTER_RE = re.compile(r"^20\d{2}(春|夏|秋|冬)季?$")
NATURES = frozenset({"必修", "任修", "限修", "选修"})
GRADE_RE = re.compile(r"^(\d{1,3}(\.\d+)?|优秀|良好|中等|及格|不及格|通过)$")

IDEOLOGY_KEYWORDS = (
    "思想道德",
    "毛泽东",
    "习近平",
    "马克思主义",
    "中国近现代史",
    "形势与政策",
    "国家安全",
    "中国共产党历史",
    "思政",
)

# 成绩单课程名 -> 清单课程名
NAME_ALIASES: dict[str, str] = {
    "工科数学分析(1)": "工科数学分析（1）",
    "工科数学分析（1）": "工科数学分析（1）",
    "工科数学分析(2)": "工科数学分析（2）",
    "工科数学分析（2）": "工科数学分析（2）",
    "离散数学(信息类)": "离散数学（信息类）",
    "离散数学（信息类）": "离散数学（信息类）",
    "数据结构与程序设计(信息类)": "数据结构与程序设计（信息类）",
    "数据结构与程序设计（信息类）": "数据结构与程序设计（信息类）",
    "大学英语B（1）": "大英B1",
    "大学英语B(1)": "大英B1",
    "大学英语B（2）": "大英B2",
    "大学英语B(2)": "大英B2",
    "大学日语（3）": "大英B3",
    "大学日语(3)": "大英B3",
    "基础物理学A(1)": "基础物理学（信息类）",
    "基础物理学A（1）": "基础物理学（信息类）",
    "基础物理学B(2)": "工科大学物理（2）",
    "基础物理学B（2）": "工科大学物理（2）",
    "概率与数理模型": "概率统计A",
}

# 清单内大英课程名
ENGLISH_COURSES = {f"大英{c}{i}" for c in "AB" for i in range(1, 5)}

COLLEGE_KEYWORDS = (
    "计算机",
    "软件",
    "虚拟",
    "智能",
    "视觉",
    "图形",
    "算法",
    "数据",
    "网络",
    "系统",
    "编程",
    "机器学习",
    "离散",
    "建模",
    "优化",
    "电子",
    "自动化",
    "数学",
)


@dataclass
class CourseRecord:
    name: str
    semester: str
    nature: str
    credit: float
    grade_raw: str
    score: Optional[float]


@dataclass
class MatchedCourse:
    catalog_name: str
    transcript_name: str
    credit: float
    score: float
    semester: str


@dataclass
class CalculationResult:
    weighted_average: float
    arithmetic_average: float
    total_credits: float
    course_count: int
    required_courses: list[MatchedCourse] = field(default_factory=list)
    elective_courses: list[MatchedCourse] = field(default_factory=list)
    elective_options: list[MatchedCourse] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def normalize_name(name: str) -> str:
    return (
        name.replace("(", "（")
        .replace(")", "）")
        .replace(" ", "")
        .strip()
    )


def parse_score(grade: str) -> Optional[float]:
    grade = grade.strip()
    if grade == "通过":
        return None
    if re.match(r"^\d", grade):
        return float(grade)
    return GRADE_TO_SCORE.get(grade)


def semester_key(semester: str) -> tuple[int, int]:
    m = re.match(r"(\d{4})(春|夏|秋|冬)", semester)
    if not m:
        return (0, 0)
    order = {"春": 1, "夏": 2, "秋": 3, "冬": 4}
    return int(m.group(1)), order[m.group(2)]


def in_semester_range(
    semester: str,
    start: tuple[int, int],
    end: tuple[int, int],
) -> bool:
    sk = semester_key(semester)
    return start <= sk <= end


def is_ideology(name: str) -> bool:
    return any(kw in name for kw in IDEOLOGY_KEYWORDS)


def is_college_course(name: str) -> bool:
    return any(kw in name for kw in COLLEGE_KEYWORDS)


def is_valid_elective_candidate(name: str) -> bool:
    if is_ideology(name):
        return False
    if any(kw in name for kw in NON_ELECTIVE_KEYWORDS):
        return False
    return is_college_course(name)


# ---------------------------------------------------------------------------
# PDF 文本提取
# ---------------------------------------------------------------------------
def read_pdf_text(pdf_path: Path, min_chars: int = 200) -> str:
    doc = fitz.open(pdf_path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    if len(text.strip()) < min_chars:
        raise RuntimeError(
            f"无法从 PDF 提取足够文本（仅 {len(text.strip())} 字符）: {pdf_path}\n"
            "请确认成绩单 PDF 含有可选中文字，或换用带文本层的 PDF。"
        )
    return text


# ---------------------------------------------------------------------------
# 解析课程清单（虚拟现实技术专业页）
# ---------------------------------------------------------------------------
def parse_vr_catalog(list_pdf: Path) -> dict[str, float]:
    """
    返回虚拟现实技术专业推免课程清单。
    以内置 VR_CATALOG 为准；若 PDF 可读则校验该页存在。
    """
    if list_pdf.is_file():
        doc = fitz.open(list_pdf)
        found = any(VR_MAJOR_MARKER in page.get_text() for page in doc)
        doc.close()
        if not found:
            raise ValueError(f"未在清单 PDF 中找到「{VR_MAJOR_MARKER}」页面")
    return dict(VR_CATALOG)


# ---------------------------------------------------------------------------
# 解析成绩单
# ---------------------------------------------------------------------------
def parse_transcript(text: str) -> list[CourseRecord]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # 定位到第一条学期行
    start = 0
    for idx, line in enumerate(lines):
        if SEMESTER_RE.match(line):
            start = idx
            break
    lines = lines[start:]

    records: list[CourseRecord] = []
    i = 0
    semester = ""

    while i < len(lines):
        line = lines[i]
        if SEMESTER_RE.match(line):
            semester = line
            i += 1
            continue
        if line == "重修":
            i += 1
            continue
        if i + 4 < len(lines) and lines[i + 1] in NATURES:
            name, nature, _hours, credit_s, grade = lines[i : i + 5]
            if not GRADE_RE.match(grade):
                i += 1
                continue
            try:
                credit = float(credit_s)
            except ValueError:
                i += 1
                continue
            score = parse_score(grade)
            records.append(
                CourseRecord(
                    name=name,
                    semester=semester,
                    nature=nature,
                    credit=credit,
                    grade_raw=grade,
                    score=score,
                )
            )
            i += 5
            continue
        i += 1

    return records


def resolve_catalog_name(transcript_name: str, catalog: dict[str, float]) -> Optional[str]:
    """将成绩单课程名映射到清单课程名。"""
    raw = transcript_name.strip()
    if raw in NAME_ALIASES:
        return NAME_ALIASES[raw]

    n = normalize_name(raw)
    if raw in catalog:
        return raw
    if n in {normalize_name(k) for k in catalog}:
        for k in catalog:
            if normalize_name(k) == n:
                return k

    # 大英系列：大学英语 B（n）-> 大英Bn
    m = re.match(r"大学英语[Bb]?[（(]?(\d)[）)]?", raw)
    if m:
        key = f"大英B{m.group(1)}"
        if key in catalog:
            return key

    for cname in catalog:
        if normalize_name(cname) == n:
            return cname

    return None


# ---------------------------------------------------------------------------
# 匹配与选修
# ---------------------------------------------------------------------------
def match_required_courses(
    records: Iterable[CourseRecord],
    catalog: dict[str, float],
    semester_start: tuple[int, int],
    semester_end: tuple[int, int],
) -> tuple[dict[str, MatchedCourse], list[CourseRecord]]:
    """
    匹配清单必修课。同一清单课只保留一条（同课重修时取较高分）。
    返回 (已匹配, 未匹配且可用于选修的候选)。
    """
    matched: dict[str, MatchedCourse] = {}
    elective_candidates: list[CourseRecord] = []

    elective_keys = {k for k in catalog if "专业选修" in k}

    for rec in records:
        if not in_semester_range(rec.semester, semester_start, semester_end):
            continue
        if rec.score is None:
            continue
        if is_ideology(rec.name):
            continue

        ckey = resolve_catalog_name(rec.name, catalog)
        if ckey and ckey in catalog and ckey not in elective_keys:
            list_credit = catalog[ckey]
            prev = matched.get(ckey)
            if prev is None or rec.score > prev.score:
                matched[ckey] = MatchedCourse(
                    catalog_name=ckey,
                    transcript_name=rec.name,
                    credit=list_credit,
                    score=rec.score,
                    semester=rec.semester,
                )
        elif is_valid_elective_candidate(rec.name):
            elective_candidates.append(rec)

    return matched, elective_candidates


def _build_elective_pool(candidates: Iterable[CourseRecord]) -> list[CourseRecord]:
    pool: list[CourseRecord] = []
    seen: set[str] = set()
    for rec in candidates:
        if rec.score is None:
            continue
        key = normalize_name(rec.name)
        if key in seen:
            continue
        seen.add(key)
        pool.append(rec)
    pool.sort(key=lambda r: (r.score or 0), reverse=True)
    return pool


def _record_to_elective_matched(rec: CourseRecord) -> MatchedCourse:
    return MatchedCourse(
        catalog_name=f"专业选修/{rec.name}",
        transcript_name=rec.name,
        credit=rec.credit,
        score=rec.score,  # type: ignore[arg-type]
        semester=rec.semester,
    )


def select_electives(
    candidates: Iterable[CourseRecord],
    min_courses: int = 4,
    min_college: int = 3,
    min_credits: float = 6.0,
) -> tuple[list[MatchedCourse], list[MatchedCourse]]:
    """
    专业选修：自选 min_courses 门，本学院不少于 min_college 门，学分不少于 min_credits。
    在可行组合中选加权平均分最高的一组。

    返回 (已选课程, 全部可选课程)。
    """
    pool = _build_elective_pool(candidates)
    all_options = [_record_to_elective_matched(r) for r in pool]

    if len(pool) < min_courses:
        return all_options, all_options

    best_combo: Optional[list[CourseRecord]] = None
    best_weighted = -1.0

    for combo in combinations(pool, min_courses):
        college_n = sum(1 for r in combo if is_college_course(r.name))
        total_cr = sum(r.credit for r in combo)
        if college_n < min_college or total_cr < min_credits:
            continue
        weighted = sum(r.score * r.credit for r in combo) / total_cr  # type: ignore[operator]
        if weighted > best_weighted:
            best_weighted = weighted
            best_combo = list(combo)

    if best_combo is None:
        pool.sort(key=lambda r: r.score or 0, reverse=True)
        best_combo = pool[:min_courses]

    selected = [_record_to_elective_matched(r) for r in best_combo]
    return selected, all_options


def calculate(
    catalog: dict[str, float],
    records: list[CourseRecord],
    semester_start: tuple[int, int] = (2023, 3),
    semester_end: tuple[int, int] = (2025, 3),
    elective_count: int = 4,
) -> CalculationResult:
    warnings: list[str] = []

    # 清单内语言课、导论、选修占位不计入「未修」警告
    skip_missing = ENGLISH_COURSES | INTRO_COURSES | {k for k in catalog if "专业选修" in k}

    matched, candidates = match_required_courses(
        records, catalog, semester_start, semester_end
    )

    # 通识导论：多门命中时只保留一门（清单要求多选一）
    intro_hits = [k for k in matched if k in INTRO_COURSES]
    if len(intro_hits) > 1:
        keep = max(intro_hits, key=lambda k: matched[k].score)
        for k in intro_hits:
            if k != keep:
                candidates.append(
                    CourseRecord(
                        name=matched[k].transcript_name,
                        semester=matched[k].semester,
                        nature="限修",
                        credit=matched[k].credit,
                        grade_raw=str(matched[k].score),
                        score=matched[k].score,
                    )
                )
                del matched[k]

    electives, elective_options = select_electives(
        candidates,
        min_courses=elective_count,
        min_college=3,
        min_credits=6.0,
    )

    all_courses = list(matched.values()) + electives
    if not all_courses:
        raise ValueError("没有可用于计算的课程，请检查 PDF 路径与学期范围")

    total_credits = sum(c.credit for c in all_courses)
    weighted = sum(c.score * c.credit for c in all_courses) / total_credits
    arithmetic = sum(c.score for c in all_courses) / len(all_courses)

    missing = [
        name
        for name in catalog
        if name not in matched
        and name not in skip_missing
        and "实验" not in name  # 实验课可能未录入或名称略异
    ]

    if len(electives) < elective_count:
        warnings.append(
            f"选修课仅选出 {len(electives)} 门（要求 {elective_count} 门），请人工核对。"
        )

    return CalculationResult(
        weighted_average=weighted,
        arithmetic_average=arithmetic,
        total_credits=total_credits,
        course_count=len(all_courses),
        required_courses=sorted(matched.values(), key=lambda c: c.catalog_name),
        elective_courses=electives,
        elective_options=elective_options,
        missing_required=missing,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def _elective_display_order(result: CalculationResult) -> list[tuple[MatchedCourse, bool]]:
    """已选选修排在最前并标记，其余可选课程按成绩降序。"""
    selected_norm = {normalize_name(c.transcript_name) for c in result.elective_courses}
    ordered: list[tuple[MatchedCourse, bool]] = [
        (c, True) for c in result.elective_courses
    ]
    rest = [
        c
        for c in result.elective_options
        if normalize_name(c.transcript_name) not in selected_norm
    ]
    rest.sort(key=lambda c: c.score, reverse=True)
    ordered.extend((c, False) for c in rest)
    return ordered


def save_csv(result: CalculationResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["推免课程加权平均分核算结果", VR_MAJOR_MARKER])
        writer.writerow(["加权平均分", f"{result.weighted_average:.2f}"])
        writer.writerow(["算术平均分", f"{result.arithmetic_average:.2f}"])
        writer.writerow(["计入课程数", result.course_count])
        writer.writerow(["计入总学分", f"{result.total_credits:.1f}"])
        writer.writerow([])

        writer.writerow(
            [
                "类别",
                "清单/课程名",
                "成绩单课程名",
                "成绩",
                "学分",
                "学期",
                "计入核算",
                "选修已选",
            ]
        )
        for c in result.required_courses:
            writer.writerow(
                [
                    "清单必修",
                    c.catalog_name,
                    c.transcript_name,
                    f"{c.score:.1f}",
                    c.credit,
                    c.semester,
                    "是",
                    "",
                ]
            )
        for c, is_selected in _elective_display_order(result):
            in_calc = is_selected
            writer.writerow(
                [
                    "专业选修",
                    c.catalog_name,
                    c.transcript_name,
                    f"{c.score:.1f}",
                    c.credit,
                    c.semester,
                    "是" if in_calc else "否",
                    "是" if is_selected else "否",
                ]
            )
        if result.missing_required:
            writer.writerow([])
            writer.writerow(["未匹配到的清单课程"])
            for name in result.missing_required:
                writer.writerow([name])


def print_report(result: CalculationResult) -> None:
    print("=" * 60)
    print("推免课程加权平均分核算结果（虚拟现实技术专业）")
    print("=" * 60)
    print(f"加权平均分: {result.weighted_average:.2f}")
    print(f"算术平均分: {result.arithmetic_average:.2f}")
    print(f"计入课程数: {result.course_count}")
    print(f"计入总学分: {result.total_credits:.1f}")
    print()

    print("【清单必修课】")
    for c in result.required_courses:
        print(
            f"  {c.catalog_name:<28} {c.score:>6.1f} 分  "
            f"{c.credit:g} 学分  ({c.transcript_name}, {c.semester})"
        )

    print()
    print("【专业选修】（前若干门为已选，计入加权平均）")
    for c, is_selected in _elective_display_order(result):
        tag = "[已选]" if is_selected else "      "
        print(
            f"  {tag} {c.transcript_name:<26} {c.score:>6.1f} 分  "
            f"{c.credit:g} 学分  ({c.semester})"
        )

    if result.missing_required:
        print()
        print("【清单中未在成绩单匹配到的课程】")
        for name in result.missing_required:
            print(f"  - {name}")

    if result.warnings:
        print()
        print("【提示】")
        for w in result.warnings:
            print(f"  ! {w}")

    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="北航推免课程加权平均分核算")
    parser.add_argument("--list", type=Path, default=DEFAULT_LIST_PDF, help="课程计算清单 PDF")
    parser.add_argument("--transcript", type=Path, default=DEFAULT_TRANSCRIPT_PDF, help="成绩单 PDF")
    parser.add_argument(
        "--semester-end",
        default="2025秋",
        help="计入学期上限，如 2025秋（默认含 2023秋-2025秋）",
    )
    parser.add_argument(
        "--semester-start",
        default="2023秋",
        help="计入学期下限",
    )
    parser.add_argument("--electives", type=int, default=4, help="专业选修门数，默认 4")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_CSV,
        help=f"结果 CSV 路径（默认 {DEFAULT_OUTPUT_CSV.name}）",
    )
    args = parser.parse_args()

    if not args.list.is_file():
        sys.exit(f"找不到课程清单: {args.list}")
    if not args.transcript.is_file():
        sys.exit(f"找不到成绩单: {args.transcript}")

    print("正在解析课程清单…")
    catalog = parse_vr_catalog(args.list)
    print(f"  已载入清单课程 {len(catalog)} 门（{VR_MAJOR_MARKER}）")

    print("正在读取成绩单…")
    transcript_text = read_pdf_text(args.transcript)
    records = parse_transcript(transcript_text)
    print(f"  已解析成绩单课程 {len(records)} 条")

    start = semester_key(args.semester_start)
    end = semester_key(args.semester_end)

    result = calculate(
        catalog,
        records,
        semester_start=start,
        semester_end=end,
        elective_count=args.electives,
    )
    print_report(result)
    save_csv(result, args.output)
    print(f"\n结果已保存至: {args.output.resolve()}")


if __name__ == "__main__":
    main()
