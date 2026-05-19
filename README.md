# 北航计算机学院 VR 专业推免加权平均分脚本

课程清单在 `calculate_tuimian_gpa.py` 的 `VR_CATALOG` 中维护；成绩单为 PDF（需可选中文字）。

计入学期、专业选修门数等固定口径见脚本顶部常量：`SEMESTER_START`、`SEMESTER_END`、`ELECTIVE_COUNT`。

## 环境

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

依赖：`pymupdf`（`import fitz`）。

## 运行

默认成绩单路径见 `DEFAULT_TRANSCRIPT_PDF`，可改代码或传 `--transcript`。

```bash
.venv/bin/python calculate_tuimian_gpa.py
.venv/bin/python calculate_tuimian_gpa.py --transcript /路径/成绩单.pdf
.venv/bin/python calculate_tuimian_gpa.py -o 结果.csv
```

## 专业选修怎么选

1. **候选池**：成绩单中在 `SEMESTER_START`～`SEMESTER_END` 内、有百分制或五级制换算分、**未**匹配到 `VR_CATALOG` 必修课；且非思政课；且课名命中 `COLLEGE_KEYWORDS`；且不含 `NON_ELECTIVE_KEYWORDS`（体育、军事、博雅等）。同课名去重。
2. **规则**（与学院清单表述一致）：选 `**ELECTIVE_COUNT` 门**（默认 4）；其中 **至少 3 门**为「本学院倾向」课（由 `COLLEGE_KEYWORDS` 判定）；**所选门次合计学分 ≥ 6**。
3. **目标**：在所有满足上述约束的组合中，取所选门次自身的**加权平均分最高**的一组；若无合法组合，则按分数从高到低取前 `ELECTIVE_COUNT` 门。
4. **输出**：终端与 CSV 会列出全部候选，已选中的几门会标出。

必修课学分以 `VR_CATALOG` 为准；专业选修学分用成绩单上的学分。