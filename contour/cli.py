# -*- coding: utf-8 -*-
"""contour 命令行入口。"""

import argparse
import sys
from typing import Optional, Sequence

from . import __version__
from .grid import (
    classify_point,
    generate_grid,
    neighbors,
    parse_grid,
    slope_stats,
    to_csv,
)
from .render import render_demo, render_sheet, render_svg


def _ensure_utf8_console() -> None:
    """尽力把标准输出与标准错误切换为 UTF-8，失败时忽略。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass


def _write_text(path: str, content: str) -> None:
    """写入 UTF-8 文本，失败时转换为中文 ValueError。"""
    if not isinstance(path, str) or path == "":
        raise ValueError("输出路径不能为空")
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
    except OSError as exc:
        raise ValueError("无法写入文件 %s：%s" % (path, exc))


def _read_text(path: str) -> str:
    """读取 UTF-8 文本，失败时转换为中文 ValueError。"""
    if not isinstance(path, str) or path == "":
        raise ValueError("输入路径不能为空")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise ValueError("无法读取文件 %s：%s" % (path, exc))
    except UnicodeDecodeError:
        raise ValueError("文件 %s 不是有效的 UTF-8 文本" % path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contour",
        description="等高线地形图读图工具：生成网格、绘制等高线、判读地形部位。",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="contour %s" % __version__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    grid_parser = subparsers.add_parser(
        "grid", help="生成含山峰与鞍部的高程网格 CSV"
    )
    grid_parser.add_argument(
        "-o", "--output", required=True, help="输出的 CSV 文件路径"
    )
    grid_parser.add_argument(
        "--size", type=int, default=11, help="网格边长，范围 5~25"
    )
    grid_parser.add_argument(
        "--seed", type=int, default=0, help="随机种子"
    )

    draw_parser = subparsers.add_parser("draw", help="绘制等高线地形图 SVG")
    draw_parser.add_argument("grid_file", help="高程网格 CSV 文件")
    draw_parser.add_argument(
        "-o", "--output", required=True, help="输出的 SVG 文件路径"
    )
    draw_parser.add_argument(
        "--interval", type=float, required=True, help="等高距，必须大于 0"
    )
    draw_parser.add_argument(
        "--labels", action="store_true", help="在等高线上标注高程"
    )

    feature_parser = subparsers.add_parser(
        "feature", help="判读指定格点的地形部位"
    )
    feature_parser.add_argument("grid_file", help="高程网格 CSV 文件")
    feature_parser.add_argument(
        "--x", type=int, required=True, help="列坐标，从 0 开始"
    )
    feature_parser.add_argument(
        "--y", type=int, required=True, help="行坐标，从 0 开始"
    )

    slope_parser = subparsers.add_parser("slope", help="统计网格的坡度分布")
    slope_parser.add_argument("grid_file", help="高程网格 CSV 文件")

    sheet_parser = subparsers.add_parser(
        "sheet", help="生成 A4 等高线练习纸 HTML"
    )
    sheet_parser.add_argument(
        "-o", "--output", required=True, help="输出的 HTML 文件路径"
    )
    sheet_parser.add_argument(
        "--count", type=int, default=6, help="题目数量，范围 1~20"
    )
    sheet_parser.add_argument(
        "--answers", action="store_true", help="附加参考答案页"
    )

    demo_parser = subparsers.add_parser(
        "demo", help="生成网格图、等高线图与地形说明 HTML"
    )
    demo_parser.add_argument(
        "-o", "--output", required=True, help="输出的 HTML 文件路径"
    )
    return parser


def _cmd_grid(args: argparse.Namespace) -> int:
    grid = generate_grid(args.size, args.seed)
    _write_text(args.output, to_csv(grid))
    print(
        "已生成 %d x %d 网格，高程范围 %.1f ~ %.1f 米，输出：%s"
        % (grid.rows, grid.cols, grid.min, grid.max, args.output)
    )
    return 0


def _cmd_draw(args: argparse.Namespace) -> int:
    grid = parse_grid(_read_text(args.grid_file))
    svg = render_svg(grid, args.interval, bool(args.labels))
    _write_text(args.output, svg)
    print(
        "已绘制等高线地形图，等高距 %s，输出：%s"
        % (args.interval, args.output)
    )
    return 0


def _cmd_feature(args: argparse.Namespace) -> int:
    grid = parse_grid(_read_text(args.grid_file))
    position = classify_point(grid, args.x, args.y)
    height = grid.cells[args.y][args.x]
    print("地形部位：%s" % position)
    print("高程：%.1f 米" % height)
    print("坐标：x=%d, y=%d" % (args.x, args.y))
    print("四邻域：")
    for direction, neighbor_x, neighbor_y, neighbor_height in neighbors(
        grid, args.x, args.y
    ):
        print(
            "  %s (x=%d, y=%d) 高程 %.1f 米"
            % (direction, neighbor_x, neighbor_y, neighbor_height)
        )
    return 0


def _cmd_slope(args: argparse.Namespace) -> int:
    grid = parse_grid(_read_text(args.grid_file))
    stats = slope_stats(grid)
    print("最陡坡度：%.2f 度" % stats.steepest)
    print("最缓坡度：%.2f 度" % stats.gentlest)
    print("平均坡度：%.2f 度" % stats.average)
    print("分级统计（共 %d 条坡线）：" % stats.total)
    print("  <15 度：%d" % stats.count_lt15)
    print("  15~25 度：%d" % stats.count_15_25)
    print("  25~35 度：%d" % stats.count_25_35)
    print("  >35 度：%d" % stats.count_gt35)
    return 0


def _cmd_sheet(args: argparse.Namespace) -> int:
    grid = generate_grid(11, 7)
    content = render_sheet(grid, args.count, bool(args.answers))
    _write_text(args.output, content)
    note = "，含参考答案" if args.answers else ""
    print(
        "已生成练习纸：%s（题目 %d 道%s）"
        % (args.output, args.count, note)
    )
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    grid = generate_grid(11, 11)
    _write_text(args.output, render_demo(grid))
    print("已生成演示页：%s" % args.output)
    return 0


def _run(args: argparse.Namespace) -> int:
    if args.command == "grid":
        return _cmd_grid(args)
    if args.command == "draw":
        return _cmd_draw(args)
    if args.command == "feature":
        return _cmd_feature(args)
    if args.command == "slope":
        return _cmd_slope(args)
    if args.command == "sheet":
        return _cmd_sheet(args)
    if args.command == "demo":
        return _cmd_demo(args)
    raise ValueError("未知子命令：%s" % args.command)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口，成功返回 0，输入错误返回 2。"""
    _ensure_utf8_console()
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (TypeError, ValueError) as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 2
