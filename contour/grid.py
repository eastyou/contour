# -*- coding: utf-8 -*-
"""高程网格的读取、生成、地形部位判定与坡度统计。

网格约定：``cells[y][x]`` 表示高程，行号 ``y`` 由北向南递增，
列号 ``x`` 由西向东递增；高程单位为米，相邻格点的水平距离统一按
100 米计（见 ``HORIZONTAL_SPACING``）。

地形部位判定规则（与 README 保持一致）：

* 山顶：该点高程不低于其四邻域，且至少有一个邻点低于该点。
* 鞍部：南北两侧都高于该点、同时东西两侧都低于该点；
  或东西两侧都高于该点、同时南北两侧都低于该点。
* 山脊：沿某一方向（南北或东西）两侧均低于该点。
* 山谷：沿某一方向（南北或东西）两侧均高于该点。
* 陡坡 / 缓坡：以上均不成立时，用邻域最大高差与水平距离
  （相邻格点按 100 米计）计算坡度角，不小于 25 度判为陡坡，否则为缓坡。
* 平地：四邻域高程与该点完全相同。
"""

import math
import random
from typing import Dict, List, Tuple

__all__ = [
    "Grid",
    "SlopeStats",
    "parse_grid",
    "generate_grid",
    "to_csv",
    "neighbors",
    "classify_point",
    "slope_stats",
]

# 陡坡与缓坡的分界角度，单位：度。
STEEP_ANGLE = 25.0

# 相邻格点的水平距离，单位：米。高程单位为米，二者相除后再取反正切得到坡度角。
HORIZONTAL_SPACING = 100.0


def _coerce_elevation(value: float, row: int, col: int) -> float:
    """把单个高程值转换为 float，并拒绝布尔值与非有限数。"""
    if isinstance(value, bool):
        raise ValueError(
            "网格第 %d 行第 %d 列不能是布尔值" % (row + 1, col + 1)
        )
    if not isinstance(value, (int, float)):
        raise ValueError(
            "网格第 %d 行第 %d 列不是数值" % (row + 1, col + 1)
        )
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(
            "网格第 %d 行第 %d 列不是有限数值" % (row + 1, col + 1)
        )
    return number


class Grid:
    """规则高程网格，行列数均不小于 2。"""

    __slots__ = ("_cells", "_rows", "_cols", "_min", "_max")

    def __init__(self, cells: Tuple[Tuple[float, ...], ...]) -> None:
        if not isinstance(cells, (tuple, list)):
            raise ValueError("网格数据必须是二维序列")
        if len(cells) == 0:
            raise ValueError("网格不能为空")
        if len(cells) < 2:
            raise ValueError("网格至少需要 2 行")
        cols = len(cells[0])
        if cols < 2:
            raise ValueError("网格至少需要 2 列")
        normalized: List[Tuple[float, ...]] = []
        for row_index, row in enumerate(cells):
            if not isinstance(row, (tuple, list)):
                raise ValueError("网格第 %d 行不是序列" % (row_index + 1))
            if len(row) != cols:
                raise ValueError(
                    "网格第 %d 行的列数与首行不一致" % (row_index + 1)
                )
            values: List[float] = []
            for col_index, raw in enumerate(row):
                values.append(_coerce_elevation(raw, row_index, col_index))
            normalized.append(tuple(values))
        self._cells = tuple(normalized)
        self._rows = len(self._cells)
        self._cols = cols
        flat: List[float] = []
        for row in self._cells:
            flat.extend(row)
        self._min = min(flat)
        self._max = max(flat)

    @property
    def cells(self) -> Tuple[Tuple[float, ...], ...]:
        """二维高程元组，``cells[y][x]``。"""
        return self._cells

    @property
    def rows(self) -> int:
        """行数（南北方向格点数）。"""
        return self._rows

    @property
    def cols(self) -> int:
        """列数（东西方向格点数）。"""
        return self._cols

    @property
    def min(self) -> float:
        """全部格点中的最低高程。"""
        return self._min

    @property
    def max(self) -> float:
        """全部格点中的最高高程。"""
        return self._max

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Grid):
            return NotImplemented
        return self._cells == other.cells

    def __repr__(self) -> str:
        return "Grid(rows=%d, cols=%d, min=%.1f, max=%.1f)" % (
            self._rows,
            self._cols,
            self._min,
            self._max,
        )


def _split_line(line: str) -> List[str]:
    """按逗号或空白切分一行，去掉行尾空字段。"""
    if "," in line:
        parts = [part.strip() for part in line.split(",")]
        while parts and parts[-1] == "":
            parts.pop()
        return parts
    return line.split()


def _is_number(token: str) -> bool:
    try:
        float(token)
    except (TypeError, ValueError):
        return False
    return True


def _parse_token(token: str, row: int, col: int) -> float:
    """解析单个数值字段，失败时抛出中文 ValueError。"""
    if token == "":
        raise ValueError("网格第 %d 行第 %d 列为空" % (row + 1, col + 1))
    try:
        number = float(token)
    except ValueError:
        raise ValueError(
            "网格第 %d 行第 %d 列不是有效数字：%s"
            % (row + 1, col + 1, token)
        )
    if not math.isfinite(number):
        raise ValueError(
            "网格第 %d 行第 %d 列不是有限数值：%s"
            % (row + 1, col + 1, token)
        )
    return number


def parse_grid(text: str) -> Grid:
    """解析 CSV 形式的高程网格文本。

    允许首行为非数值表头（会被跳过），其余每行必须是等宽的数值。
    空文本、只有表头、行列不齐、非数值或非有限值都会抛出 ValueError。
    """
    if not isinstance(text, str):
        raise ValueError("网格文本必须是字符串")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line != ""]
    if not lines:
        raise ValueError("网格数据为空，无法解析")
    table: List[List[str]] = []
    for line in lines:
        tokens = _split_line(line)
        if tokens:
            table.append(tokens)
    if not table:
        raise ValueError("网格数据为空，无法解析")
    start = 0
    if any(not _is_number(token) for token in table[0]):
        start = 1
    data = table[start:]
    if not data:
        raise ValueError("网格只有表头，缺少数据行")
    width = len(data[0])
    if width < 2:
        raise ValueError("网格至少需要 2 列")
    cells: List[Tuple[float, ...]] = []
    for row_index, tokens in enumerate(data):
        if len(tokens) != width:
            raise ValueError(
                "网格第 %d 行的列数与首行不一致" % (row_index + 1)
            )
        values: List[float] = []
        for col_index, token in enumerate(tokens):
            values.append(_parse_token(token, row_index, col_index))
        cells.append(tuple(values))
    return Grid(tuple(cells))


def _format_number(value: float) -> str:
    return "%.1f" % value


def to_csv(grid: Grid) -> str:
    """把网格序列化成 CSV 文本，首行为列名表头。"""
    if not isinstance(grid, Grid):
        raise ValueError("to_csv 需要一个 Grid 实例")
    header = ",".join("C%d" % col for col in range(grid.cols))
    lines: List[str] = [header]
    for row in grid.cells:
        lines.append(",".join(_format_number(value) for value in row))
    return "\n".join(lines) + "\n"


def generate_grid(size: int, seed: int = 0) -> Grid:
    """生成含两座山峰及其鞍部的确定性高程网格。"""
    if isinstance(size, bool) or not isinstance(size, int):
        raise ValueError("网格尺寸必须是整数")
    if size < 5 or size > 25:
        raise ValueError("网格尺寸必须在 5 到 25 之间")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("随机种子必须是整数")
    rng = random.Random(seed)
    base = float(rng.randint(100, 160))
    sigma = size * 0.22
    denominator = 2.0 * sigma * sigma
    peaks: List[Tuple[float, float, float]] = [
        (size * 0.28, size * 0.32, float(rng.randint(240, 300))),
        (size * 0.72, size * 0.62, float(rng.randint(280, 340))),
    ]
    ripple_amp = rng.uniform(2.0, 6.0)
    ripple_x = rng.uniform(0.5, 1.1)
    ripple_y = rng.uniform(0.5, 1.1)
    cells: List[Tuple[float, ...]] = []
    for y in range(size):
        row: List[float] = []
        for x in range(size):
            height = base
            for peak_x, peak_y, amplitude in peaks:
                distance2 = (x - peak_x) ** 2 + (y - peak_y) ** 2
                height += amplitude * math.exp(-distance2 / denominator)
            height += ripple_amp * math.sin(x * ripple_x) * math.cos(
                y * ripple_y
            )
            row.append(round(height, 1))
        cells.append(tuple(row))
    return Grid(tuple(cells))


def _check_point(grid: Grid, x: int, y: int) -> None:
    if not isinstance(grid, Grid):
        raise ValueError("需要一个 Grid 实例")
    if isinstance(x, bool) or not isinstance(x, int):
        raise ValueError("x 坐标必须是整数")
    if isinstance(y, bool) or not isinstance(y, int):
        raise ValueError("y 坐标必须是整数")
    if x < 0 or x >= grid.cols:
        raise ValueError(
            "x 坐标越界：%d（有效范围 0..%d）" % (x, grid.cols - 1)
        )
    if y < 0 or y >= grid.rows:
        raise ValueError(
            "y 坐标越界：%d（有效范围 0..%d）" % (y, grid.rows - 1)
        )


def neighbors(
    grid: Grid, x: int, y: int
) -> List[Tuple[str, int, int, float]]:
    """返回四邻域中实际存在的格点：``(方向, x, y, 高程)``。"""
    _check_point(grid, x, y)
    result: List[Tuple[str, int, int, float]] = []
    if y > 0:
        result.append(("北", x, y - 1, grid.cells[y - 1][x]))
    if y < grid.rows - 1:
        result.append(("南", x, y + 1, grid.cells[y + 1][x]))
    if x > 0:
        result.append(("西", x - 1, y, grid.cells[y][x - 1]))
    if x < grid.cols - 1:
        result.append(("东", x + 1, y, grid.cells[y][x + 1]))
    return result


def classify_point(grid: Grid, x: int, y: int) -> str:
    """判定指定格点的地形部位，返回中文名称。"""
    _check_point(grid, x, y)
    center = grid.cells[y][x]
    deltas: Dict[str, float] = {}
    for name, _, _, height in neighbors(grid, x, y):
        deltas[name] = height - center
    values = list(deltas.values())
    if all(delta == 0.0 for delta in values):
        return "平地"
    if all(delta <= 0.0 for delta in values):
        return "山顶"
    north = deltas.get("北")
    south = deltas.get("南")
    east = deltas.get("东")
    west = deltas.get("西")
    if north is not None and south is not None:
        if north > 0.0 and south > 0.0:
            if east is not None and west is not None:
                if east < 0.0 and west < 0.0:
                    return "鞍部"
        if north < 0.0 and south < 0.0:
            if east is not None and west is not None:
                if east > 0.0 and west > 0.0:
                    return "鞍部"
    if north is not None and south is not None:
        if north < 0.0 and south < 0.0:
            return "山脊"
    if east is not None and west is not None:
        if east < 0.0 and west < 0.0:
            return "山脊"
    if north is not None and south is not None:
        if north > 0.0 and south > 0.0:
            return "山谷"
    if east is not None and west is not None:
        if east > 0.0 and west > 0.0:
            return "山谷"
    steepest = max(abs(delta) for delta in values)
    angle = math.degrees(math.atan2(steepest, HORIZONTAL_SPACING))
    if angle >= STEEP_ANGLE:
        return "陡坡"
    return "缓坡"


class SlopeStats:
    """坡度统计结果，角度单位为度。"""

    __slots__ = (
        "steepest",
        "gentlest",
        "average",
        "count_lt15",
        "count_15_25",
        "count_25_35",
        "count_gt35",
        "total",
    )

    def __init__(
        self,
        steepest: float,
        gentlest: float,
        average: float,
        count_lt15: int,
        count_15_25: int,
        count_25_35: int,
        count_gt35: int,
        total: int,
    ) -> None:
        self.steepest = steepest
        self.gentlest = gentlest
        self.average = average
        self.count_lt15 = count_lt15
        self.count_15_25 = count_15_25
        self.count_25_35 = count_25_35
        self.count_gt35 = count_gt35
        self.total = total

    def as_dict(self) -> Dict[str, float]:
        """按键值对形式返回统计结果，便于输出。"""
        return {
            "steepest": self.steepest,
            "gentlest": self.gentlest,
            "average": self.average,
            "count_lt15": float(self.count_lt15),
            "count_15_25": float(self.count_15_25),
            "count_25_35": float(self.count_25_35),
            "count_gt35": float(self.count_gt35),
            "total": float(self.total),
        }

    def __repr__(self) -> str:
        return (
            "SlopeStats(steepest=%.2f, gentlest=%.2f, average=%.2f, total=%d)"
            % (self.steepest, self.gentlest, self.average, self.total)
        )


def slope_stats(grid: Grid) -> SlopeStats:
    """统计全部相邻格点连线的坡度角分布。"""
    if not isinstance(grid, Grid):
        raise ValueError("slope_stats 需要一个 Grid 实例")
    slopes: List[float] = []
    for y in range(grid.rows):
        for x in range(grid.cols):
            if x + 1 < grid.cols:
                drop = abs(grid.cells[y][x + 1] - grid.cells[y][x])
                slopes.append(
                    math.degrees(math.atan2(drop, HORIZONTAL_SPACING))
                )
            if y + 1 < grid.rows:
                drop = abs(grid.cells[y + 1][x] - grid.cells[y][x])
                slopes.append(
                    math.degrees(math.atan2(drop, HORIZONTAL_SPACING))
                )
    if not slopes:
        raise ValueError("网格太小，无法计算坡度")
    steepest = max(slopes)
    gentlest = min(slopes)
    average = sum(slopes) / float(len(slopes))
    count_lt15 = 0
    count_15_25 = 0
    count_25_35 = 0
    count_gt35 = 0
    for angle in slopes:
        if angle < 15.0:
            count_lt15 += 1
        elif angle < 25.0:
            count_15_25 += 1
        elif angle < 35.0:
            count_25_35 += 1
        else:
            count_gt35 += 1
    return SlopeStats(
        steepest=steepest,
        gentlest=gentlest,
        average=average,
        count_lt15=count_lt15,
        count_15_25=count_15_25,
        count_25_35=count_25_35,
        count_gt35=count_gt35,
        total=len(slopes),
    )
