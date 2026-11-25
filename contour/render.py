# -*- coding: utf-8 -*-
"""等高线提取与 SVG / HTML 渲染。

所有标记文本均通过 :func:`html.escape` 转义后再拼接，
不依赖 ``xml.etree`` 等第三方或标准库 XML 组件。
"""

import html
import math
from typing import Dict, List, Tuple

from .grid import Grid, classify_point

__all__ = [
    "marching_squares",
    "render_svg",
    "render_grid_map",
    "render_sheet",
    "render_demo",
]

# 边索引：0=上边，1=右边，2=下边，3=左边。
_CASE_PAIRS: Dict[int, Tuple[Tuple[int, int], ...]] = {
    1: ((3, 2),),
    2: ((2, 1),),
    3: ((3, 1),),
    4: ((0, 1),),
    5: ((0, 1), (3, 2)),
    6: ((0, 2),),
    7: ((3, 0),),
    8: ((0, 3),),
    9: ((0, 2),),
    10: ((0, 3), (2, 1)),
    11: ((0, 1),),
    12: ((3, 1),),
    13: ((2, 1),),
    14: ((3, 2),),
}


def _interp(first: float, second: float, level: float) -> float:
    """计算等值线与一条边的交点在边上的比例位置。"""
    diff = second - first
    if abs(diff) < 1e-12:
        return 0.5
    ratio = (level - first) / diff
    if ratio < 0.0:
        return 0.0
    if ratio > 1.0:
        return 1.0
    return ratio


def marching_squares(
    grid: Grid, level: float
) -> List[Tuple[float, float, float, float]]:
    """用 marching squares 提取一条等值线，返回线段列表。

    每条线段为 ``(x1, y1, x2, y2)``，坐标单位是格点索引。
    ``level`` 超出网格高程范围时返回空列表。
    """
    if not isinstance(grid, Grid):
        raise ValueError("marching_squares 需要一个 Grid 实例")
    if isinstance(level, bool) or not isinstance(level, (int, float)):
        raise ValueError("等值线高程必须是数值")
    level_value = float(level)
    if not math.isfinite(level_value):
        raise ValueError("等值线高程必须是有限数值")
    if level_value < grid.min or level_value > grid.max:
        return []
    segments: List[Tuple[float, float, float, float]] = []
    for y in range(grid.rows - 1):
        row_top = grid.cells[y]
        row_bottom = grid.cells[y + 1]
        for x in range(grid.cols - 1):
            top_left = row_top[x]
            top_right = row_top[x + 1]
            bottom_right = row_bottom[x + 1]
            bottom_left = row_bottom[x]
            case_index = 0
            if top_left >= level_value:
                case_index |= 8
            if top_right >= level_value:
                case_index |= 4
            if bottom_right >= level_value:
                case_index |= 2
            if bottom_left >= level_value:
                case_index |= 1
            if case_index == 0 or case_index == 15:
                continue
            top = (x + _interp(top_left, top_right, level_value), float(y))
            right = (
                float(x + 1),
                y + _interp(top_right, bottom_right, level_value),
            )
            bottom = (
                x + _interp(bottom_left, bottom_right, level_value),
                float(y + 1),
            )
            left = (
                float(x),
                y + _interp(top_left, bottom_left, level_value),
            )
            points = (top, right, bottom, left)
            for first_index, second_index in _CASE_PAIRS[case_index]:
                first = points[first_index]
                second = points[second_index]
                segments.append(
                    (
                        round(first[0], 4),
                        round(first[1], 4),
                        round(second[0], 4),
                        round(second[1], 4),
                    )
                )
    return segments


def _format_level(level: float) -> str:
    rounded = round(level)
    if abs(level - rounded) < 1e-9:
        return "%d" % int(rounded)
    return ("%.2f" % level).rstrip("0").rstrip(".")


def _levels(grid: Grid, interval: float) -> List[float]:
    """从高于最低点的下一个 interval 倍数开始生成等高线层级。"""
    low = grid.min
    high = grid.max
    if high <= low:
        return []
    base = math.floor(low / interval) * interval
    level = base + interval
    levels: List[float] = []
    steps = 0
    while level <= high + 1e-9 and steps < 100000:
        levels.append(round(level, 6))
        level += interval
        steps += 1
    return levels


def render_svg(grid: Grid, interval: float, labels: bool) -> str:
    """渲染等高线地形图 SVG 字符串。"""
    if not isinstance(grid, Grid):
        raise ValueError("render_svg 需要一个 Grid 实例")
    if isinstance(interval, bool) or not isinstance(interval, (int, float)):
        raise ValueError("等高距必须是数值")
    interval_value = float(interval)
    if not math.isfinite(interval_value) or interval_value <= 0.0:
        raise ValueError("等高距必须大于 0")
    cell = 36
    margin = 72
    plot_width = grid.cols * cell
    plot_height = grid.rows * cell
    width = plot_width + margin * 2
    height = plot_height + margin * 2

    def sx(point_x: float) -> float:
        return margin + point_x * cell

    def sy(point_y: float) -> float:
        return margin + point_y * cell

    levels = _levels(grid, interval_value)
    paths: List[str] = []
    label_parts: List[str] = []
    for level in levels:
        segments = marching_squares(grid, level)
        if not segments:
            continue
        commands: List[str] = []
        for x1, y1, x2, y2 in segments:
            commands.append(
                "M %.2f %.2f L %.2f %.2f"
                % (sx(x1), sy(y1), sx(x2), sy(y2))
            )
        paths.append('<path d="%s"/>' % " ".join(commands))
        if labels:
            x1, y1, x2, y2 = segments[0]
            label_x = sx((x1 + x2) / 2.0) + 3.0
            label_y = sy((y1 + y2) / 2.0) - 3.0
            label_parts.append(
                '<text x="%.2f" y="%.2f" font-size="10" fill="#6b3f1d">%s</text>'
                % (label_x, label_y, html.escape(_format_level(level)))
            )

    title = "等高线地形图"
    subtitle = "等高距 %s 米" % _format_level(interval_value)
    scale_note = (
        "比例说明：相邻格点水平距离按 100 米计，等高距为 %s 米。"
        % _format_level(interval_value)
    )
    range_note = "高程范围 %.1f ~ %.1f 米" % (grid.min, grid.max)

    north_x = width - margin / 2.0
    parts: List[str] = []
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d"'
        ' viewBox="0 0 %d %d" role="img">'
        % (width, height, width, height)
    )
    parts.append("<title>%s</title>" % html.escape(title))
    parts.append("<desc>%s</desc>" % html.escape(scale_note))
    parts.append(
        '<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>'
        % (width, height)
    )
    parts.append(
        '<text x="%d" y="32" font-size="18" font-weight="bold"'
        ' fill="#1f1f1f">%s</text>' % (margin, html.escape(title))
    )
    parts.append(
        '<text x="%d" y="52" font-size="13" fill="#444444">%s</text>'
        % (margin, html.escape(subtitle))
    )
    parts.append(
        '<rect x="%d" y="%d" width="%d" height="%d" fill="none"'
        ' stroke="#555555" stroke-width="1"/>'
        % (margin, margin, plot_width, plot_height)
    )
    parts.append(
        '<g fill="none" stroke="#8b5a2b" stroke-width="1.4"'
        ' stroke-linejoin="round">'
    )
    parts.extend(paths)
    parts.append("</g>")
    parts.append('<g fill="none" stroke="none">')
    parts.extend(label_parts)
    parts.append("</g>")
    parts.append(
        '<g id="north-arrow">'
        '<polygon points="%.2f,18 %.2f,58 %.2f,58" fill="#333333"/>'
        '<text x="%.2f" y="74" text-anchor="middle" font-size="14"'
        ' fill="#333333">N</text></g>'
        % (north_x, north_x - 10.0, north_x + 10.0, north_x)
    )
    parts.append(
        '<text x="%d" y="%d" font-size="12" fill="#444444">%s</text>'
        % (margin, height - 30, html.escape(range_note))
    )
    parts.append(
        '<text x="%d" y="%d" font-size="12" fill="#444444">%s</text>'
        % (margin, height - 12, html.escape(scale_note))
    )
    parts.append("</svg>")
    return "".join(parts)


def _color_for(value: float, low: float, high: float) -> str:
    """按高程在低到高之间插值出棕绿色。"""
    if high <= low:
        ratio = 0.5
    else:
        ratio = (value - low) / (high - low)
    if ratio < 0.0:
        ratio = 0.0
    elif ratio > 1.0:
        ratio = 1.0
    red = int(round(232 + (150 - 232) * ratio))
    green = int(round(244 + (110 - 244) * ratio))
    blue = int(round(233 + (70 - 233) * ratio))
    return "#%02x%02x%02x" % (red, green, blue)


def render_grid_map(grid: Grid, cell: int = 30) -> str:
    """渲染带高程数字的彩色网格图 SVG 字符串。"""
    if not isinstance(grid, Grid):
        raise ValueError("render_grid_map 需要一个 Grid 实例")
    if isinstance(cell, bool) or not isinstance(cell, int) or cell <= 0:
        raise ValueError("格宽必须是正整数")
    margin = 24
    width = grid.cols * cell + margin * 2
    height = grid.rows * cell + margin * 2
    parts: List[str] = []
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d"'
        ' viewBox="0 0 %d %d" role="img">'
        % (width, height, width, height)
    )
    parts.append("<title>%s</title>" % html.escape("高程网格图"))
    parts.append(
        '<desc>%s</desc>'
        % html.escape("方格内数字为高程，颜色越深表示地势越高。")
    )
    parts.append(
        '<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>'
        % (width, height)
    )
    for y in range(grid.rows):
        for x in range(grid.cols):
            value = grid.cells[y][x]
            color = _color_for(value, grid.min, grid.max)
            pixel_x = margin + x * cell
            pixel_y = margin + y * cell
            parts.append(
                '<rect x="%d" y="%d" width="%d" height="%d" fill="%s"'
                ' stroke="#3f3f3f" stroke-width="0.5"/>'
                % (pixel_x, pixel_y, cell, cell, color)
            )
            if cell >= 28:
                parts.append(
                    '<text x="%.1f" y="%.1f" text-anchor="middle"'
                    ' font-size="9" fill="#1a1a1a">%s</text>'
                    % (
                        pixel_x + cell / 2.0,
                        pixel_y + cell / 2.0 + 3.0,
                        html.escape("%.0f" % value),
                    )
                )
    parts.append("</svg>")
    return "".join(parts)


def _sheet_interval(grid: Grid) -> float:
    """为练习纸挑选一个合适的等高距。"""
    span = grid.max - grid.min
    if span <= 0.0:
        return 10.0
    rough = span / 6.0
    if rough <= 0.0:
        return 10.0
    magnitude = 10 ** math.floor(math.log10(rough))
    step = magnitude * 10.0
    for factor in (1.0, 2.0, 5.0, 10.0):
        if rough <= factor * magnitude:
            step = factor * magnitude
            break
    if step <= 0.0:
        step = 10.0
    return float(step)


def _pick_point(grid: Grid, index: int) -> Tuple[int, int]:
    column = (index * 3 + 1) % grid.cols
    row = (index * 5 + 2) % grid.rows
    return column, row


def _build_questions(
    grid: Grid, count: int
) -> Tuple[List[str], List[str]]:
    """生成练习题目与参考答案文本。"""
    questions: List[str] = []
    answers: List[str] = []
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for index in range(count):
        kind = index % 3
        if kind == 0:
            column, row = _pick_point(grid, index)
            name = letters[index % len(letters)]
            position = classify_point(grid, column, row)
            height = grid.cells[row][column]
            questions.append(
                "图中点 %s（第 %d 列，第 %d 行，高程 %.1f 米）"
                "属于哪种地形部位？"
                % (name, column + 1, row + 1, height)
            )
            answers.append(
                "第 %d 题：点 %s 位于%s。" % (index + 1, name, position)
            )
        elif kind == 1:
            first_x, first_y = _pick_point(grid, index)
            second_x, second_y = _pick_point(grid, index + 7)
            if first_x == second_x and first_y == second_y:
                second_x = (second_x + 1) % grid.cols
            first_height = grid.cells[first_y][first_x]
            second_height = grid.cells[second_y][second_x]
            difference = abs(first_height - second_height)
            questions.append(
                "计算点 P（第 %d 列，第 %d 行）与点 Q（第 %d 列，"
                "第 %d 行）的相对高度。"
                % (first_x + 1, first_y + 1, second_x + 1, second_y + 1)
            )
            answers.append(
                "第 %d 题：相对高度约为 %.1f 米（%.1f 与 %.1f 之差）。"
                % (
                    index + 1,
                    difference,
                    max(first_height, second_height),
                    min(first_height, second_height),
                )
            )
        else:
            first_x, first_y = _pick_point(grid, index)
            second_x, second_y = _pick_point(grid, index + 3)
            if first_x == second_x and first_y == second_y:
                second_y = (second_y + 1) % grid.rows
            first_position = classify_point(grid, first_x, first_y)
            second_position = classify_point(grid, second_x, second_y)
            questions.append(
                "比较点 M（第 %d 列，第 %d 行，高程 %.1f 米）与点 N"
                "（第 %d 列，第 %d 行，高程 %.1f 米）所在坡的陡缓，"
                "并说明判断依据。"
                % (
                    first_x + 1,
                    first_y + 1,
                    grid.cells[first_y][first_x],
                    second_x + 1,
                    second_y + 1,
                    grid.cells[second_y][second_x],
                )
            )
            answers.append(
                "第 %d 题：点 M 为%s，点 N 为%s；等高线越密集，坡度越陡。"
                % (index + 1, first_position, second_position)
            )
    return questions, answers


def _sheet_css() -> str:
    return (
        "@page { size: A4; margin: 12mm; }"
        "body { margin: 0; background: #f2f2f2; color: #1f1f1f;"
        ' font-family: "Songti SC", "SimSun", serif; }'
        ".sheet { width: 210mm; min-height: 297mm; box-sizing: border-box;"
        " padding: 14mm; margin: 0 auto 12mm; background: #ffffff; }"
        ".sheet header h1 { font-size: 20px; margin: 0 0 6px; }"
        ".sheet .meta { font-size: 13px; color: #444444; margin: 0 0 10px; }"
        ".figure { border: 1px solid #dddddd; padding: 4px; margin: 0 0 10px; }"
        ".figure svg { width: 100%; height: auto; display: block; }"
        ".questions { font-size: 14px; line-height: 1.9; padding-left: 22px; }"
        ".questions li { margin-bottom: 10px; }"
        ".legend { width: 100%; border-collapse: collapse; font-size: 13px; }"
        ".legend th, .legend td { border: 1px solid #cccccc; padding: 6px 8px;"
        " text-align: left; }"
        ".answers h1 { font-size: 18px; margin: 0 0 10px; }"
        ".answers ol { font-size: 13px; line-height: 1.8; padding-left: 22px; }"
        "@media print { body { background: #ffffff; }"
        ".sheet { margin: 0; page-break-after: always; } }"
    )


def render_sheet(grid: Grid, count: int, answers: bool) -> str:
    """渲染 A4 等高线练习纸 HTML 字符串。"""
    if not isinstance(grid, Grid):
        raise ValueError("render_sheet 需要一个 Grid 实例")
    if isinstance(count, bool) or not isinstance(count, int):
        raise ValueError("题目数量必须是整数")
    if count < 1 or count > 20:
        raise ValueError("题目数量必须在 1 到 20 之间")
    if not isinstance(answers, bool):
        raise ValueError("answers 参数必须是布尔值")
    interval = _sheet_interval(grid)
    figure = render_svg(grid, interval, False)
    questions, answer_lines = _build_questions(grid, count)
    parts: List[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="zh-CN">')
    parts.append("<head>")
    parts.append('<meta charset="utf-8"/>')
    parts.append(
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>'
    )
    parts.append("<title>%s</title>" % html.escape("等高线地形图练习"))
    parts.append("<style>%s</style>" % _sheet_css())
    parts.append("</head>")
    parts.append("<body>")
    parts.append('<main class="sheet">')
    parts.append("<header>")
    parts.append("<h1>%s</h1>" % html.escape("等高线地形图练习"))
    parts.append(
        '<p class="meta">%s</p>'
        % html.escape("姓名：__________ 班级：__________ 得分：______")
    )
    parts.append(
        '<p class="meta">%s</p>'
        % html.escape(
            "说明：本图等高距 %s 米，相邻格点水平距离按 100 米计。"
            % _format_level(interval)
        )
    )
    parts.append("</header>")
    parts.append('<div class="figure">')
    parts.append(figure)
    parts.append("</div>")
    parts.append('<ol class="questions">')
    for question in questions:
        parts.append("<li>%s</li>" % html.escape(question))
    parts.append("</ol>")
    parts.append("</main>")
    if answers:
        parts.append('<main class="sheet answers">')
        parts.append("<h1>%s</h1>" % html.escape("参考答案"))
        parts.append("<ol>")
        for line in answer_lines:
            parts.append("<li>%s</li>" % html.escape(line))
        parts.append("</ol>")
        parts.append("</main>")
    parts.append("</body>")
    parts.append("</html>")
    return "".join(parts)


def render_demo(grid: Grid) -> str:
    """渲染包含网格图、等高线图与地形部位说明的演示页 HTML。"""
    if not isinstance(grid, Grid):
        raise ValueError("render_demo 需要一个 Grid 实例")
    interval = _sheet_interval(grid)
    grid_map = render_grid_map(grid)
    contour_map = render_svg(grid, interval, True)
    explanations: Tuple[Tuple[str, str], ...] = (
        ("山顶", "等高线呈闭合曲线，数值由中心向四周降低。"),
        ("鞍部", "两个山顶之间的低洼处，南北或东西两侧同时升高。"),
        ("山脊", "等高线向低处凸出，沿某一方向两侧均降低。"),
        ("山谷", "等高线向高处凸出，沿某一方向两侧均升高。"),
        ("陡坡", "等高线密集，邻域高差大，坡度角不小于 25 度。"),
        ("缓坡", "等高线稀疏，邻域高差小，坡度角小于 25 度。"),
        ("平地", "四邻域高程与该点相同，坡度为 0 度。"),
    )
    parts: List[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="zh-CN">')
    parts.append("<head>")
    parts.append('<meta charset="utf-8"/>')
    parts.append(
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>'
    )
    parts.append("<title>%s</title>" % html.escape("等高线读图演示"))
    parts.append("<style>%s</style>" % _sheet_css())
    parts.append("</head>")
    parts.append("<body>")
    parts.append('<main class="sheet">')
    parts.append("<header>")
    parts.append("<h1>%s</h1>" % html.escape("等高线读图演示"))
    parts.append(
        '<p class="meta">%s</p>'
        % html.escape(
            "高程范围 %.1f ~ %.1f 米，等高距 %s 米。"
            % (grid.min, grid.max, _format_level(interval))
        )
    )
    parts.append("</header>")
    parts.append("<h2>%s</h2>" % html.escape("一、高程网格图"))
    parts.append('<div class="figure">')
    parts.append(grid_map)
    parts.append("</div>")
    parts.append("<h2>%s</h2>" % html.escape("二、等高线地形图"))
    parts.append('<div class="figure">')
    parts.append(contour_map)
    parts.append("</div>")
    parts.append("<h2>%s</h2>" % html.escape("三、地形部位说明"))
    parts.append('<table class="legend">')
    parts.append(
        "<tr><th>%s</th><th>%s</th></tr>"
        % (html.escape("部位"), html.escape("判读要点"))
    )
    for name, description in explanations:
        parts.append(
            "<tr><td>%s</td><td>%s</td></tr>"
            % (html.escape(name), html.escape(description))
        )
    parts.append("</table>")
    parts.append("</main>")
    parts.append("</body>")
    parts.append("</html>")
    return "".join(parts)
