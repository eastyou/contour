# -*- coding: utf-8 -*-
"""contour：初中地理等高线地形图读图工具。

对外暴露网格读取与地形判定 API，以及等高线与练习纸的渲染函数。
"""

__version__ = "0.1.0"

from .grid import (  # noqa: E402
    Grid,
    SlopeStats,
    classify_point,
    generate_grid,
    neighbors,
    parse_grid,
    slope_stats,
    to_csv,
)
from .render import (  # noqa: E402
    marching_squares,
    render_demo,
    render_grid_map,
    render_sheet,
    render_svg,
)

__all__ = [
    "Grid",
    "SlopeStats",
    "__version__",
    "classify_point",
    "generate_grid",
    "marching_squares",
    "neighbors",
    "parse_grid",
    "render_demo",
    "render_grid_map",
    "render_sheet",
    "render_svg",
    "slope_stats",
    "to_csv",
]
