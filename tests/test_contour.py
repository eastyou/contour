# -*- coding: utf-8 -*-
"""contour 的单元测试，全部基于标准库 unittest。"""

import contextlib
import io
import math
import os
import tempfile
import unittest
from html.parser import HTMLParser
from typing import Dict, List, Tuple

from contour import (
    Grid,
    SlopeStats,
    __version__,
    classify_point,
    generate_grid,
    marching_squares,
    neighbors,
    parse_grid,
    render_demo,
    render_grid_map,
    render_sheet,
    render_svg,
    slope_stats,
    to_csv,
)
from contour.cli import main
from contour.grid import HORIZONTAL_SPACING

VALID_FEATURES = ("山顶", "鞍部", "山脊", "山谷", "陡坡", "缓坡", "平地")


class _TagChecker(HTMLParser):
    """记录标签闭合情况，用于验证 HTML / SVG 结构完整。"""

    _VOID = frozenset(
        [
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        ]
    )

    def __init__(self) -> None:
        HTMLParser.__init__(self, convert_charrefs=True)
        self.stack: List[str] = []
        self.mismatches: List[str] = []

    def handle_starttag(
        self, tag: str, attrs: List[Tuple[str, str]]
    ) -> None:
        if tag not in self._VOID:
            self.stack.append(tag)

    def handle_startendtag(
        self, tag: str, attrs: List[Tuple[str, str]]
    ) -> None:
        return None

    def handle_endtag(self, tag: str) -> None:
        if tag in self._VOID:
            return
        if not self.stack:
            self.mismatches.append("多余的结束标签：%s" % tag)
            return
        if self.stack[-1] == tag:
            self.stack.pop()
            return
        if tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.mismatches.append("未闭合标签：%s" % self.stack.pop())
            if self.stack:
                self.stack.pop()
            return
        self.mismatches.append("多余的结束标签：%s" % tag)


def _check_html(testcase: unittest.TestCase, text: str) -> None:
    parser = _TagChecker()
    parser.feed(text)
    parser.close()
    testcase.assertEqual(parser.mismatches, [])
    testcase.assertEqual(parser.stack, [])


def _run_main(arguments: List[str]) -> Tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out):
        with contextlib.redirect_stderr(err):
            code = main(arguments)
    return code, out.getvalue(), err.getvalue()


def _write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _run_main_with_exit(
    arguments: List[str],
) -> Tuple[int, str, str, int]:
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out):
        with contextlib.redirect_stderr(err):
            try:
                code = main(arguments)
            except SystemExit as exc:
                return 0, out.getvalue(), err.getvalue(), int(exc.code)
    return code, out.getvalue(), err.getvalue(), -1


def _count_local_maxima(grid: Grid) -> int:
    total = 0
    for y in range(grid.rows):
        for x in range(grid.cols):
            height = grid.cells[y][x]
            if all(
                neighbor_height <= height
                for _, _, _, neighbor_height in neighbors(grid, x, y)
            ):
                total += 1
    return total


class TestGridBasics(unittest.TestCase):
    def test_rows_and_cols(self) -> None:
        grid = Grid(((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)))
        self.assertEqual(grid.rows, 2)
        self.assertEqual(grid.cols, 3)

    def test_min_and_max(self) -> None:
        grid = Grid(((3.0, 9.0), (-1.0, 4.0)))
        self.assertEqual(grid.min, -1.0)
        self.assertEqual(grid.max, 9.0)

    def test_cells_are_tuples(self) -> None:
        grid = Grid(((1, 2), (3, 4)))
        self.assertIsInstance(grid.cells, tuple)
        self.assertIsInstance(grid.cells[0], tuple)
        self.assertEqual(grid.cells[1][0], 3.0)

    def test_equality(self) -> None:
        first = Grid(((1.0, 2.0), (3.0, 4.0)))
        second = Grid(((1.0, 2.0), (3.0, 4.0)))
        third = Grid(((1.0, 2.0), (3.0, 5.0)))
        self.assertEqual(first, second)
        self.assertNotEqual(first, third)

    def test_repr_contains_dimensions(self) -> None:
        text = repr(Grid(((1.0, 2.0), (3.0, 4.0))))
        self.assertIn("rows=2", text)
        self.assertIn("cols=2", text)

    def test_reject_empty(self) -> None:
        with self.assertRaises(ValueError):
            Grid(())

    def test_reject_single_row(self) -> None:
        with self.assertRaises(ValueError):
            Grid(((1.0, 2.0),))

    def test_reject_single_column(self) -> None:
        with self.assertRaises(ValueError):
            Grid(((1.0,), (2.0,)))

    def test_reject_ragged_rows(self) -> None:
        with self.assertRaises(ValueError):
            Grid(((1.0, 2.0), (3.0,)))

    def test_reject_bool(self) -> None:
        with self.assertRaises(ValueError):
            Grid(((True, 2.0), (3.0, 4.0)))

    def test_reject_non_numeric(self) -> None:
        with self.assertRaises(ValueError):
            Grid((("a", 2.0), (3.0, 4.0)))

    def test_reject_nan(self) -> None:
        with self.assertRaises(ValueError):
            Grid(((float("nan"), 2.0), (3.0, 4.0)))

    def test_reject_infinity(self) -> None:
        with self.assertRaises(ValueError):
            Grid(((float("inf"), 2.0), (3.0, 4.0)))

    def test_accept_nested_lists(self) -> None:
        grid = Grid([[1, 2], [3, 4]])
        self.assertEqual(grid.rows, 2)
        self.assertEqual(grid.cells[0], (1.0, 2.0))

    def test_negative_elevations_allowed(self) -> None:
        grid = Grid(((-5.0, -1.0), (-2.0, 0.0)))
        self.assertEqual(grid.min, -5.0)


class TestParseGrid(unittest.TestCase):
    def test_parse_plain_numbers(self) -> None:
        grid = parse_grid("1 2\n3 4")
        self.assertEqual(grid.rows, 2)
        self.assertEqual(grid.cols, 2)
        self.assertEqual(grid.cells[1][1], 4.0)

    def test_parse_comma_separated(self) -> None:
        grid = parse_grid("1,2\n3,4")
        self.assertEqual(grid.cells[0], (1.0, 2.0))

    def test_parse_with_header(self) -> None:
        grid = parse_grid("C0,C1\n1,2\n3,4")
        self.assertEqual(grid.rows, 2)
        self.assertEqual(grid.max, 4.0)

    def test_parse_ignores_blank_lines(self) -> None:
        grid = parse_grid("C0,C1\n\n1,2\n   \n3,4\n")
        self.assertEqual(grid.rows, 2)

    def test_parse_trailing_commas(self) -> None:
        grid = parse_grid("1,2,\n3,4,\n")
        self.assertEqual(grid.rows, 2)
        self.assertEqual(grid.cols, 2)

    def test_parse_negative_values(self) -> None:
        grid = parse_grid("-1,2\n3,-4")
        self.assertEqual(grid.min, -4.0)

    def test_parse_decimals(self) -> None:
        grid = parse_grid("1.5,2.25\n3.0,4.75")
        self.assertAlmostEqual(grid.cells[0][1], 2.25)

    def test_empty_text_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_grid("")

    def test_whitespace_only_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_grid("   \n\n  ")

    def test_only_header_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_grid("C0,C1\n")

    def test_ragged_rows_raise(self) -> None:
        with self.assertRaises(ValueError):
            parse_grid("1,2\n3,4,5")

    def test_non_numeric_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_grid("1,2\n3,abc")

    def test_empty_cell_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_grid("1,2\n,4")

    def test_nan_token_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_grid("1,2\n3,nan")

    def test_inf_token_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_grid("1,2\n3,inf")

    def test_single_column_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_grid("1\n2\n3")

    def test_single_row_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_grid("1,2,3")

    def test_non_string_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_grid(123)  # type: ignore[arg-type]

    def test_to_csv_has_header(self) -> None:
        text = to_csv(Grid(((1.0, 2.0), (3.0, 4.0))))
        self.assertTrue(text.startswith("C0,C1"))

    def test_to_csv_roundtrip(self) -> None:
        original = Grid(((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)))
        restored = parse_grid(to_csv(original))
        self.assertEqual(original, restored)

    def test_to_csv_rejects_non_grid(self) -> None:
        with self.assertRaises(ValueError):
            to_csv("not a grid")  # type: ignore[arg-type]


class TestGenerateGrid(unittest.TestCase):
    def test_default_shape(self) -> None:
        grid = generate_grid(11, 7)
        self.assertEqual(grid.rows, 11)
        self.assertEqual(grid.cols, 11)

    def test_minimum_size(self) -> None:
        grid = generate_grid(5, 1)
        self.assertEqual(grid.rows, 5)

    def test_maximum_size(self) -> None:
        grid = generate_grid(25, 1)
        self.assertEqual(grid.cols, 25)

    def test_reproducible_with_same_seed(self) -> None:
        first = generate_grid(9, 3)
        second = generate_grid(9, 3)
        self.assertEqual(first, second)

    def test_different_seed_changes_grid(self) -> None:
        first = generate_grid(9, 3)
        second = generate_grid(9, 4)
        self.assertNotEqual(first, second)

    def test_has_relief(self) -> None:
        grid = generate_grid(11, 7)
        self.assertLess(grid.min, grid.max)

    def test_contains_local_maxima(self) -> None:
        grid = generate_grid(11, 7)
        self.assertGreaterEqual(_count_local_maxima(grid), 1)

    def test_size_too_small_raises(self) -> None:
        with self.assertRaises(ValueError):
            generate_grid(4, 0)

    def test_size_too_large_raises(self) -> None:
        with self.assertRaises(ValueError):
            generate_grid(26, 0)

    def test_size_not_int_raises(self) -> None:
        with self.assertRaises(ValueError):
            generate_grid("11", 0)  # type: ignore[arg-type]

    def test_size_bool_raises(self) -> None:
        with self.assertRaises(ValueError):
            generate_grid(True, 0)  # type: ignore[arg-type]

    def test_seed_not_int_raises(self) -> None:
        with self.assertRaises(ValueError):
            generate_grid(11, "7")  # type: ignore[arg-type]

    def test_negative_seed_allowed(self) -> None:
        grid = generate_grid(9, -5)
        self.assertEqual(grid.rows, 9)


class TestNeighbors(unittest.TestCase):
    def setUp(self) -> None:
        self.grid = Grid(
            (
                (1.0, 2.0, 3.0),
                (4.0, 5.0, 6.0),
                (7.0, 8.0, 9.0),
            )
        )

    def test_center_has_four_neighbors(self) -> None:
        self.assertEqual(len(neighbors(self.grid, 1, 1)), 4)

    def test_corner_has_two_neighbors(self) -> None:
        self.assertEqual(len(neighbors(self.grid, 0, 0)), 2)

    def test_edge_has_three_neighbors(self) -> None:
        self.assertEqual(len(neighbors(self.grid, 1, 0)), 3)

    def test_direction_names(self) -> None:
        names = [item[0] for item in neighbors(self.grid, 1, 1)]
        self.assertEqual(sorted(names), sorted(["北", "南", "东", "西"]))

    def test_neighbor_values_match_grid(self) -> None:
        mapping = {
            name: height for name, _, _, height in neighbors(self.grid, 1, 1)
        }
        self.assertEqual(mapping["北"], 2.0)
        self.assertEqual(mapping["南"], 8.0)
        self.assertEqual(mapping["西"], 4.0)
        self.assertEqual(mapping["东"], 6.0)

    def test_x_out_of_range_raises(self) -> None:
        with self.assertRaises(ValueError):
            neighbors(self.grid, 3, 0)

    def test_y_out_of_range_raises(self) -> None:
        with self.assertRaises(ValueError):
            neighbors(self.grid, 0, 3)

    def test_negative_coordinate_raises(self) -> None:
        with self.assertRaises(ValueError):
            neighbors(self.grid, -1, 0)

    def test_non_integer_coordinate_raises(self) -> None:
        with self.assertRaises(ValueError):
            neighbors(self.grid, 1.5, 0)  # type: ignore[arg-type]

    def test_bool_coordinate_raises(self) -> None:
        with self.assertRaises(ValueError):
            neighbors(self.grid, True, 0)  # type: ignore[arg-type]

    def test_non_grid_raises(self) -> None:
        with self.assertRaises(ValueError):
            neighbors("grid", 0, 0)  # type: ignore[arg-type]


class TestClassifyPoint(unittest.TestCase):
    def test_peak_center(self) -> None:
        grid = Grid(
            (
                (1.0, 1.0, 1.0),
                (1.0, 9.0, 1.0),
                (1.0, 1.0, 1.0),
            )
        )
        self.assertEqual(classify_point(grid, 1, 1), "山顶")

    def test_flat_center(self) -> None:
        grid = Grid(((5.0, 5.0), (5.0, 5.0)))
        self.assertEqual(classify_point(grid, 0, 0), "平地")

    def test_ridge_center(self) -> None:
        grid = Grid(
            (
                (0.0, 0.0, 0.0),
                (5.0, 10.0, 20.0),
                (0.0, 0.0, 0.0),
            )
        )
        self.assertEqual(classify_point(grid, 1, 1), "山脊")

    def test_valley_center(self) -> None:
        grid = Grid(
            (
                (9.0, 9.0, 9.0),
                (9.0, 5.0, 9.0),
                (9.0, 9.0, 9.0),
            )
        )
        self.assertEqual(classify_point(grid, 1, 1), "山谷")

    def test_saddle_center(self) -> None:
        grid = Grid(
            (
                (0.0, 10.0, 0.0),
                (2.0, 5.0, 2.0),
                (0.0, 10.0, 0.0),
            )
        )
        self.assertEqual(classify_point(grid, 1, 1), "鞍部")

    def test_steep_slope(self) -> None:
        grid = Grid(
            (
                (10.0, 0.0, 10.0),
                (10.0, 10.0, 100.0),
                (10.0, 10.0, 10.0),
            )
        )
        self.assertEqual(classify_point(grid, 1, 1), "陡坡")

    def test_gentle_slope(self) -> None:
        grid = Grid(
            (
                (10.0, 10.0, 10.0),
                (10.0, 10.0, 10.2),
                (10.0, 10.0, 10.0),
            )
        )
        self.assertEqual(classify_point(grid, 1, 1), "缓坡")

    def test_corner_peak(self) -> None:
        grid = Grid(((9.0, 1.0), (1.0, 1.0)))
        self.assertEqual(classify_point(grid, 0, 0), "山顶")

    def test_result_in_valid_set(self) -> None:
        grid = generate_grid(11, 7)
        for y in range(grid.rows):
            for x in range(grid.cols):
                self.assertIn(classify_point(grid, x, y), VALID_FEATURES)

    def test_x_out_of_range_raises(self) -> None:
        grid = Grid(((1.0, 2.0), (3.0, 4.0)))
        with self.assertRaises(ValueError):
            classify_point(grid, 2, 0)

    def test_y_out_of_range_raises(self) -> None:
        grid = Grid(((1.0, 2.0), (3.0, 4.0)))
        with self.assertRaises(ValueError):
            classify_point(grid, 0, 2)

    def test_negative_coordinate_raises(self) -> None:
        grid = Grid(((1.0, 2.0), (3.0, 4.0)))
        with self.assertRaises(ValueError):
            classify_point(grid, 0, -1)

    def test_bool_coordinate_raises(self) -> None:
        grid = Grid(((1.0, 2.0), (3.0, 4.0)))
        with self.assertRaises(ValueError):
            classify_point(grid, True, 0)  # type: ignore[arg-type]


class TestSlopeStats(unittest.TestCase):
    def test_flat_grid_zero_slopes(self) -> None:
        grid = Grid(((5.0, 5.0, 5.0), (5.0, 5.0, 5.0), (5.0, 5.0, 5.0)))
        stats = slope_stats(grid)
        self.assertEqual(stats.steepest, 0.0)
        self.assertEqual(stats.gentlest, 0.0)
        self.assertEqual(stats.average, 0.0)

    def test_flat_grid_bucket_counts(self) -> None:
        grid = Grid(((5.0, 5.0, 5.0), (5.0, 5.0, 5.0), (5.0, 5.0, 5.0)))
        stats = slope_stats(grid)
        self.assertEqual(stats.total, 12)
        self.assertEqual(stats.count_lt15, 12)
        self.assertEqual(stats.count_15_25, 0)
        self.assertEqual(stats.count_25_35, 0)
        self.assertEqual(stats.count_gt35, 0)

    def test_single_step(self) -> None:
        grid = Grid(((0.0, 100.0), (100.0, 100.0)))
        stats = slope_stats(grid)
        self.assertAlmostEqual(stats.steepest, 45.0)
        self.assertAlmostEqual(stats.gentlest, 0.0)
        self.assertAlmostEqual(stats.average, 22.5)

    def test_bucket_15_to_25(self) -> None:
        value = HORIZONTAL_SPACING * math.tan(math.radians(20.0))
        grid = Grid(((0.0, value), (0.0, 0.0)))
        stats = slope_stats(grid)
        self.assertEqual(stats.count_15_25, 2)
        self.assertEqual(stats.count_lt15, 2)

    def test_bucket_25_to_35(self) -> None:
        value = HORIZONTAL_SPACING * math.tan(math.radians(30.0))
        grid = Grid(((0.0, value), (0.0, 0.0)))
        stats = slope_stats(grid)
        self.assertEqual(stats.count_25_35, 2)

    def test_bucket_above_35(self) -> None:
        value = HORIZONTAL_SPACING * math.tan(math.radians(40.0))
        grid = Grid(((0.0, value), (0.0, 0.0)))
        stats = slope_stats(grid)
        self.assertEqual(stats.count_gt35, 2)

    def test_counts_sum_to_total(self) -> None:
        grid = generate_grid(11, 7)
        stats = slope_stats(grid)
        self.assertEqual(
            stats.count_lt15
            + stats.count_15_25
            + stats.count_25_35
            + stats.count_gt35,
            stats.total,
        )

    def test_steepest_not_below_gentlest(self) -> None:
        stats = slope_stats(generate_grid(9, 2))
        self.assertGreaterEqual(stats.steepest, stats.gentlest)

    def test_average_within_range(self) -> None:
        stats = slope_stats(generate_grid(9, 2))
        self.assertGreaterEqual(stats.average, stats.gentlest)
        self.assertLessEqual(stats.average, stats.steepest)

    def test_total_equals_edge_count(self) -> None:
        grid = Grid(((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)))
        expected = grid.rows * (grid.cols - 1) + grid.cols * (grid.rows - 1)
        self.assertEqual(slope_stats(grid).total, expected)

    def test_as_dict_keys(self) -> None:
        data = slope_stats(Grid(((0.0, 1.0), (1.0, 1.0)))).as_dict()
        self.assertEqual(len(data), 8)
        self.assertIn("steepest", data)
        self.assertIn("total", data)

    def test_repr_contains_name(self) -> None:
        self.assertIn("SlopeStats", repr(slope_stats(Grid(((0.0, 1.0), (1.0, 1.0))))))

    def test_non_grid_raises(self) -> None:
        with self.assertRaises(ValueError):
            slope_stats("grid")  # type: ignore[arg-type]

    def test_instance_type(self) -> None:
        self.assertIsInstance(slope_stats(Grid(((0.0, 1.0), (1.0, 1.0)))), SlopeStats)


class TestMarchingSquares(unittest.TestCase):
    def test_flat_grid_returns_empty(self) -> None:
        grid = Grid(((5.0, 5.0), (5.0, 5.0)))
        self.assertEqual(marching_squares(grid, 5.0), [])

    def test_level_above_range_returns_empty(self) -> None:
        grid = Grid(((0.0, 1.0), (0.0, 1.0)))
        self.assertEqual(marching_squares(grid, 100.0), [])

    def test_level_below_range_returns_empty(self) -> None:
        grid = Grid(((0.0, 1.0), (0.0, 1.0)))
        self.assertEqual(marching_squares(grid, -100.0), [])

    def test_vertical_segment(self) -> None:
        grid = Grid(((0.0, 10.0), (0.0, 10.0)))
        segments = marching_squares(grid, 5.0)
        self.assertEqual(len(segments), 1)
        self.assertAlmostEqual(segments[0][0], 0.5, places=4)
        self.assertAlmostEqual(segments[0][1], 0.0, places=4)
        self.assertAlmostEqual(segments[0][2], 0.5, places=4)
        self.assertAlmostEqual(segments[0][3], 1.0, places=4)

    def test_horizontal_segment(self) -> None:
        grid = Grid(((0.0, 0.0), (10.0, 10.0)))
        segments = marching_squares(grid, 5.0)
        self.assertEqual(len(segments), 1)
        self.assertAlmostEqual(segments[0][0], 0.0, places=4)
        self.assertAlmostEqual(segments[0][1], 0.5, places=4)
        self.assertAlmostEqual(segments[0][2], 1.0, places=4)
        self.assertAlmostEqual(segments[0][3], 0.5, places=4)

    def test_saddle_cell_has_two_segments(self) -> None:
        grid = Grid(((10.0, 0.0), (0.0, 10.0)))
        self.assertEqual(len(marching_squares(grid, 5.0)), 2)

    def test_multi_cell_segment_count(self) -> None:
        grid = Grid(((0.0, 10.0), (0.0, 10.0), (0.0, 10.0)))
        self.assertEqual(len(marching_squares(grid, 5.0)), 2)

    def test_segment_has_four_coordinates(self) -> None:
        segments = marching_squares(generate_grid(9, 3), 200.0)
        self.assertGreater(len(segments), 0)
        for segment in segments:
            self.assertEqual(len(segment), 4)

    def test_coordinates_within_bounds(self) -> None:
        grid = generate_grid(9, 3)
        for segment in marching_squares(grid, 200.0):
            for index in (0, 2):
                self.assertGreaterEqual(segment[index], 0.0)
                self.assertLessEqual(segment[index], float(grid.cols - 1))
            for index in (1, 3):
                self.assertGreaterEqual(segment[index], 0.0)
                self.assertLessEqual(segment[index], float(grid.rows - 1))

    def test_level_not_number_raises(self) -> None:
        grid = Grid(((0.0, 1.0), (0.0, 1.0)))
        with self.assertRaises(ValueError):
            marching_squares(grid, "5")  # type: ignore[arg-type]

    def test_level_nan_raises(self) -> None:
        grid = Grid(((0.0, 1.0), (0.0, 1.0)))
        with self.assertRaises(ValueError):
            marching_squares(grid, float("nan"))

    def test_level_bool_raises(self) -> None:
        grid = Grid(((0.0, 1.0), (0.0, 1.0)))
        with self.assertRaises(ValueError):
            marching_squares(grid, True)  # type: ignore[arg-type]

    def test_non_grid_raises(self) -> None:
        with self.assertRaises(ValueError):
            marching_squares("grid", 5.0)  # type: ignore[arg-type]

    def test_level_at_max_returns_segment(self) -> None:
        grid = Grid(((0.0, 10.0), (0.0, 10.0)))
        self.assertEqual(len(marching_squares(grid, 10.0)), 1)


class TestRenderSvg(unittest.TestCase):
    def setUp(self) -> None:
        self.grid = generate_grid(9, 3)

    def test_returns_svg_document(self) -> None:
        svg = render_svg(self.grid, 20, False)
        self.assertTrue(svg.startswith("<svg"))
        self.assertTrue(svg.endswith("</svg>"))

    def test_has_xmlns(self) -> None:
        svg = render_svg(self.grid, 20, False)
        self.assertIn('xmlns="http://www.w3.org/2000/svg"', svg)

    def test_contains_title(self) -> None:
        svg = render_svg(self.grid, 20, False)
        self.assertIn("等高线地形图", svg)

    def test_contains_scale_note(self) -> None:
        svg = render_svg(self.grid, 20, False)
        self.assertIn("比例说明", svg)

    def test_contains_north_arrow(self) -> None:
        svg = render_svg(self.grid, 20, False)
        self.assertIn("north-arrow", svg)
        self.assertIn("polygon", svg)

    def test_parseable_by_html_parser(self) -> None:
        _check_html(self, render_svg(self.grid, 20, True))

    def test_labels_add_text(self) -> None:
        svg = render_svg(Grid(((0.0, 10.0), (0.0, 10.0))), 4, True)
        self.assertIn(">4<", svg)
        self.assertIn(">8<", svg)

    def test_interval_zero_raises(self) -> None:
        with self.assertRaises(ValueError):
            render_svg(self.grid, 0, False)

    def test_interval_negative_raises(self) -> None:
        with self.assertRaises(ValueError):
            render_svg(self.grid, -5, False)

    def test_interval_nan_raises(self) -> None:
        with self.assertRaises(ValueError):
            render_svg(self.grid, float("nan"), False)

    def test_interval_not_number_raises(self) -> None:
        with self.assertRaises(ValueError):
            render_svg(self.grid, "20", False)  # type: ignore[arg-type]

    def test_non_grid_raises(self) -> None:
        with self.assertRaises(ValueError):
            render_svg("grid", 20, False)  # type: ignore[arg-type]

    def test_flat_grid_renders_without_paths(self) -> None:
        flat = Grid(((5.0, 5.0), (5.0, 5.0)))
        svg = render_svg(flat, 10, False)
        self.assertNotIn("<path", svg)

    def test_levels_start_at_next_multiple(self) -> None:
        svg = render_svg(Grid(((0.0, 10.0), (0.0, 10.0))), 4, False)
        self.assertEqual(svg.count("<path"), 2)

    def test_contains_range_note(self) -> None:
        svg = render_svg(self.grid, 20, False)
        self.assertIn("高程范围", svg)


class TestRenderGridMap(unittest.TestCase):
    def test_returns_svg(self) -> None:
        svg = render_grid_map(Grid(((1.0, 2.0), (3.0, 4.0))))
        self.assertTrue(svg.startswith("<svg"))
        self.assertTrue(svg.endswith("</svg>"))

    def test_parseable_by_html_parser(self) -> None:
        _check_html(self, render_grid_map(generate_grid(5, 1)))

    def test_contains_values(self) -> None:
        svg = render_grid_map(Grid(((1.0, 2.0), (3.0, 4.0))))
        self.assertIn(">4<", svg)

    def test_cell_zero_raises(self) -> None:
        with self.assertRaises(ValueError):
            render_grid_map(Grid(((1.0, 2.0), (3.0, 4.0))), 0)

    def test_cell_bool_raises(self) -> None:
        with self.assertRaises(ValueError):
            render_grid_map(Grid(((1.0, 2.0), (3.0, 4.0))), True)  # type: ignore[arg-type]

    def test_non_grid_raises(self) -> None:
        with self.assertRaises(ValueError):
            render_grid_map("grid")  # type: ignore[arg-type]


class TestRenderSheet(unittest.TestCase):
    def setUp(self) -> None:
        self.grid = generate_grid(11, 7)

    def test_returns_html(self) -> None:
        text = render_sheet(self.grid, 6, False)
        self.assertTrue(text.startswith("<!DOCTYPE html>"))
        self.assertTrue(text.endswith("</html>"))

    def test_parseable_by_html_parser(self) -> None:
        _check_html(self, render_sheet(self.grid, 6, True))

    def test_a4_css_present(self) -> None:
        self.assertIn("@page", render_sheet(self.grid, 6, False))
        self.assertIn("A4", render_sheet(self.grid, 6, False))

    def test_question_count(self) -> None:
        text = render_sheet(self.grid, 4, False)
        self.assertEqual(text.count("<li>"), 4)

    def test_answers_double_items(self) -> None:
        text = render_sheet(self.grid, 4, True)
        self.assertEqual(text.count("<li>"), 8)
        self.assertIn("参考答案", text)

    def test_no_answers_page_by_default(self) -> None:
        text = render_sheet(self.grid, 3, False)
        self.assertNotIn("参考答案", text)

    def test_contains_question_keywords(self) -> None:
        text = render_sheet(self.grid, 6, False)
        self.assertIn("地形部位", text)
        self.assertIn("相对高度", text)
        self.assertIn("陡缓", text)

    def test_contains_contour_svg(self) -> None:
        text = render_sheet(self.grid, 6, False)
        self.assertIn("<svg", text)
        self.assertIn("等高线地形图", text)

    def test_count_zero_raises(self) -> None:
        with self.assertRaises(ValueError):
            render_sheet(self.grid, 0, False)

    def test_count_too_large_raises(self) -> None:
        with self.assertRaises(ValueError):
            render_sheet(self.grid, 21, False)

    def test_count_not_int_raises(self) -> None:
        with self.assertRaises(ValueError):
            render_sheet(self.grid, "6", False)  # type: ignore[arg-type]

    def test_count_bool_raises(self) -> None:
        with self.assertRaises(ValueError):
            render_sheet(self.grid, True, False)  # type: ignore[arg-type]

    def test_answers_not_bool_raises(self) -> None:
        with self.assertRaises(ValueError):
            render_sheet(self.grid, 3, "yes")  # type: ignore[arg-type]

    def test_non_grid_raises(self) -> None:
        with self.assertRaises(ValueError):
            render_sheet("grid", 3, False)  # type: ignore[arg-type]

    def test_single_question(self) -> None:
        self.assertEqual(render_sheet(self.grid, 1, False).count("<li>"), 1)


class TestRenderDemo(unittest.TestCase):
    def setUp(self) -> None:
        self.grid = generate_grid(11, 11)

    def test_returns_html(self) -> None:
        text = render_demo(self.grid)
        self.assertTrue(text.startswith("<!DOCTYPE html>"))
        self.assertTrue(text.endswith("</html>"))

    def test_parseable_by_html_parser(self) -> None:
        _check_html(self, render_demo(self.grid))

    def test_contains_three_sections(self) -> None:
        text = render_demo(self.grid)
        self.assertIn("高程网格图", text)
        self.assertIn("等高线地形图", text)
        self.assertIn("地形部位说明", text)

    def test_contains_feature_names(self) -> None:
        text = render_demo(self.grid)
        for name in VALID_FEATURES:
            self.assertIn(name, text)

    def test_contains_svg_maps(self) -> None:
        self.assertEqual(render_demo(self.grid).count("<svg"), 2)

    def test_non_grid_raises(self) -> None:
        with self.assertRaises(ValueError):
            render_demo("grid")  # type: ignore[arg-type]


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.directory = self._temp.name

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _path(self, name: str) -> str:
        return os.path.join(self.directory, name)

    def _make_grid(self, name: str = "grid.csv") -> str:
        path = self._path(name)
        _write_text(path, to_csv(generate_grid(9, 3)))
        return path

    def _read(self, path: str) -> str:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()


class TestCliGrid(CliTestCase):
    def test_default_grid(self) -> None:
        path = self._path("grid.csv")
        code, stdout, _ = _run_main(["grid", "-o", path])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(path))
        self.assertIn("已生成", stdout)
        self.assertEqual(parse_grid(self._read(path)).rows, 11)

    def test_custom_size_and_seed(self) -> None:
        path = self._path("grid.csv")
        code, _, _ = _run_main(
            ["grid", "-o", path, "--size", "7", "--seed", "5"]
        )
        self.assertEqual(code, 0)
        grid = parse_grid(self._read(path))
        self.assertEqual(grid.rows, 7)
        self.assertEqual(grid.cols, 7)

    def test_reproducible_seed(self) -> None:
        first = self._path("first.csv")
        second = self._path("second.csv")
        _run_main(["grid", "-o", first, "--size", "7", "--seed", "9"])
        _run_main(["grid", "-o", second, "--size", "7", "--seed", "9"])
        self.assertEqual(self._read(first), self._read(second))

    def test_size_too_small_returns_two(self) -> None:
        code, _, err = _run_main(
            ["grid", "-o", self._path("g.csv"), "--size", "4"]
        )
        self.assertEqual(code, 2)
        self.assertIn("错误：", err)

    def test_size_too_large_returns_two(self) -> None:
        code, _, err = _run_main(
            ["grid", "-o", self._path("g.csv"), "--size", "26"]
        )
        self.assertEqual(code, 2)
        self.assertIn("错误：", err)

    def test_bad_output_path_returns_two(self) -> None:
        path = os.path.join(self.directory, "missing", "g.csv")
        code, _, err = _run_main(["grid", "-o", path])
        self.assertEqual(code, 2)
        self.assertIn("错误：", err)

    def test_size_not_integer_exits_two(self) -> None:
        code, _, _, exit_code = _run_main_with_exit(
            ["grid", "-o", self._path("g.csv"), "--size", "abc"]
        )
        self.assertEqual(exit_code, 2)
        self.assertEqual(code, 0)


class TestCliDraw(CliTestCase):
    def test_creates_svg(self) -> None:
        grid_path = self._make_grid()
        output = self._path("contour.svg")
        code, stdout, _ = _run_main(
            ["draw", grid_path, "-o", output, "--interval", "20"]
        )
        self.assertEqual(code, 0)
        self.assertIn("已绘制", stdout)
        self.assertTrue(self._read(output).startswith("<svg"))

    def test_output_parseable(self) -> None:
        grid_path = self._make_grid()
        output = self._path("contour.svg")
        _run_main(["draw", grid_path, "-o", output, "--interval", "20"])
        _check_html(self, self._read(output))

    def test_labels_flag(self) -> None:
        grid_path = self._path("small.csv")
        _write_text(grid_path, "0,10\n0,10\n")
        output = self._path("labelled.svg")
        code, _, _ = _run_main(
            ["draw", grid_path, "-o", output, "--interval", "4", "--labels"]
        )
        self.assertEqual(code, 0)
        text = self._read(output)
        self.assertIn(">4<", text)
        self.assertIn(">8<", text)

    def test_interval_zero_returns_two(self) -> None:
        grid_path = self._make_grid()
        code, _, err = _run_main(
            [
                "draw",
                grid_path,
                "-o",
                self._path("c.svg"),
                "--interval",
                "0",
            ]
        )
        self.assertEqual(code, 2)
        self.assertIn("错误：", err)

    def test_interval_negative_returns_two(self) -> None:
        grid_path = self._make_grid()
        code, _, err = _run_main(
            [
                "draw",
                grid_path,
                "-o",
                self._path("c.svg"),
                "--interval",
                "-5",
            ]
        )
        self.assertEqual(code, 2)
        self.assertIn("错误：", err)

    def test_missing_grid_file_returns_two(self) -> None:
        code, _, err = _run_main(
            [
                "draw",
                self._path("none.csv"),
                "-o",
                self._path("c.svg"),
                "--interval",
                "20",
            ]
        )
        self.assertEqual(code, 2)
        self.assertIn("错误：", err)

    def test_malformed_grid_returns_two(self) -> None:
        grid_path = self._path("bad.csv")
        _write_text(grid_path, "1,2\n3\n")
        code, _, err = _run_main(
            ["draw", grid_path, "-o", self._path("c.svg"), "--interval", "20"]
        )
        self.assertEqual(code, 2)
        self.assertIn("错误：", err)

    def test_interval_not_number_exits_two(self) -> None:
        grid_path = self._make_grid()
        code, _, _, exit_code = _run_main_with_exit(
            [
                "draw",
                grid_path,
                "-o",
                self._path("c.svg"),
                "--interval",
                "abc",
            ]
        )
        self.assertEqual(exit_code, 2)
        self.assertEqual(code, 0)


class TestCliFeature(CliTestCase):
    def test_reports_feature(self) -> None:
        grid_path = self._make_grid()
        code, stdout, _ = _run_main(
            ["feature", grid_path, "--x", "4", "--y", "4"]
        )
        self.assertEqual(code, 0)
        self.assertIn("地形部位：", stdout)
        self.assertIn("高程：", stdout)

    def test_reports_coordinates(self) -> None:
        grid_path = self._make_grid()
        _, stdout, _ = _run_main(
            ["feature", grid_path, "--x", "2", "--y", "6"]
        )
        self.assertIn("x=2, y=6", stdout)

    def test_reports_neighbors(self) -> None:
        grid_path = self._make_grid()
        _, stdout, _ = _run_main(
            ["feature", grid_path, "--x", "4", "--y", "4"]
        )
        self.assertIn("四邻域：", stdout)
        for direction in ("北", "南", "东", "西"):
            self.assertIn(direction, stdout)

    def test_x_out_of_range_returns_two(self) -> None:
        grid_path = self._make_grid()
        code, _, err = _run_main(
            ["feature", grid_path, "--x", "99", "--y", "4"]
        )
        self.assertEqual(code, 2)
        self.assertIn("错误：", err)

    def test_y_out_of_range_returns_two(self) -> None:
        grid_path = self._make_grid()
        code, _, err = _run_main(
            ["feature", grid_path, "--x", "4", "--y", "-1"]
        )
        self.assertEqual(code, 2)
        self.assertIn("错误：", err)

    def test_missing_file_returns_two(self) -> None:
        code, _, err = _run_main(
            ["feature", self._path("none.csv"), "--x", "1", "--y", "1"]
        )
        self.assertEqual(code, 2)
        self.assertIn("错误：", err)

    def test_non_integer_coordinate_exits_two(self) -> None:
        grid_path = self._make_grid()
        code, _, _, exit_code = _run_main_with_exit(
            ["feature", grid_path, "--x", "a", "--y", "1"]
        )
        self.assertEqual(exit_code, 2)
        self.assertEqual(code, 0)


class TestCliSlope(CliTestCase):
    def test_reports_all_sections(self) -> None:
        grid_path = self._make_grid()
        code, stdout, _ = _run_main(["slope", grid_path])
        self.assertEqual(code, 0)
        self.assertIn("最陡坡度：", stdout)
        self.assertIn("最缓坡度：", stdout)
        self.assertIn("平均坡度：", stdout)
        self.assertIn("<15 度：", stdout)
        self.assertIn("15~25 度：", stdout)
        self.assertIn("25~35 度：", stdout)
        self.assertIn(">35 度：", stdout)

    def test_flat_grid_zero_slope(self) -> None:
        grid_path = self._path("flat.csv")
        _write_text(grid_path, "5,5\n5,5\n")
        code, stdout, _ = _run_main(["slope", grid_path])
        self.assertEqual(code, 0)
        self.assertIn("最陡坡度：0.00 度", stdout)

    def test_missing_file_returns_two(self) -> None:
        code, _, err = _run_main(["slope", self._path("none.csv")])
        self.assertEqual(code, 2)
        self.assertIn("错误：", err)

    def test_malformed_file_returns_two(self) -> None:
        grid_path = self._path("bad.csv")
        _write_text(grid_path, "1,2\n3,four\n")
        code, _, err = _run_main(["slope", grid_path])
        self.assertEqual(code, 2)
        self.assertIn("错误：", err)


class TestCliSheetAndDemo(CliTestCase):
    def test_sheet_creates_html(self) -> None:
        output = self._path("sheet.html")
        code, stdout, _ = _run_main(["sheet", "-o", output])
        self.assertEqual(code, 0)
        self.assertIn("已生成练习纸", stdout)
        self.assertEqual(self._read(output).count("<li>"), 6)

    def test_sheet_parseable(self) -> None:
        output = self._path("sheet.html")
        _run_main(["sheet", "-o", output, "--count", "4"])
        _check_html(self, self._read(output))

    def test_sheet_with_answers(self) -> None:
        output = self._path("sheet.html")
        code, _, _ = _run_main(
            ["sheet", "-o", output, "--count", "4", "--answers"]
        )
        self.assertEqual(code, 0)
        text = self._read(output)
        self.assertEqual(text.count("<li>"), 8)
        self.assertIn("参考答案", text)

    def test_sheet_invalid_count_returns_two(self) -> None:
        code, _, err = _run_main(
            ["sheet", "-o", self._path("s.html"), "--count", "0"]
        )
        self.assertEqual(code, 2)
        self.assertIn("错误：", err)

    def test_sheet_count_too_large_returns_two(self) -> None:
        code, _, err = _run_main(
            ["sheet", "-o", self._path("s.html"), "--count", "21"]
        )
        self.assertEqual(code, 2)
        self.assertIn("错误：", err)

    def test_sheet_bad_output_returns_two(self) -> None:
        path = os.path.join(self.directory, "missing", "s.html")
        code, _, err = _run_main(["sheet", "-o", path])
        self.assertEqual(code, 2)
        self.assertIn("错误：", err)

    def test_demo_creates_html(self) -> None:
        output = self._path("demo.html")
        code, stdout, _ = _run_main(["demo", "-o", output])
        self.assertEqual(code, 0)
        self.assertIn("已生成演示页", stdout)
        text = self._read(output)
        self.assertIn("地形部位说明", text)
        self.assertEqual(text.count("<svg"), 2)

    def test_demo_parseable(self) -> None:
        output = self._path("demo.html")
        _run_main(["demo", "-o", output])
        _check_html(self, self._read(output))

    def test_demo_bad_output_returns_two(self) -> None:
        path = os.path.join(self.directory, "missing", "d.html")
        code, _, err = _run_main(["demo", "-o", path])
        self.assertEqual(code, 2)
        self.assertIn("错误：", err)


class TestCliGeneral(CliTestCase):
    def test_help_exits_zero(self) -> None:
        code, stdout, _, exit_code = _run_main_with_exit(["--help"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(code, 0)
        self.assertIn("grid", stdout)
        self.assertIn("sheet", stdout)

    def test_version_exits_zero(self) -> None:
        code, stdout, _, exit_code = _run_main_with_exit(["--version"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(code, 0)
        self.assertIn("0.1.0", stdout)

    def test_no_arguments_exits_two(self) -> None:
        _, _, _, exit_code = _run_main_with_exit([])
        self.assertEqual(exit_code, 2)

    def test_unknown_command_exits_two(self) -> None:
        _, _, _, exit_code = _run_main_with_exit(["unknown"])
        self.assertEqual(exit_code, 2)

    def test_draw_requires_interval(self) -> None:
        grid_path = self._make_grid()
        _, _, _, exit_code = _run_main_with_exit(
            ["draw", grid_path, "-o", self._path("c.svg")]
        )
        self.assertEqual(exit_code, 2)

    def test_sheet_requires_output(self) -> None:
        _, _, _, exit_code = _run_main_with_exit(["sheet"])
        self.assertEqual(exit_code, 2)


class TestPublicApi(unittest.TestCase):
    def test_version_string(self) -> None:
        self.assertEqual(__version__, "0.1.0")

    def test_callables_exposed(self) -> None:
        for function in (
            classify_point,
            generate_grid,
            marching_squares,
            neighbors,
            parse_grid,
            render_demo,
            render_grid_map,
            render_sheet,
            render_svg,
            slope_stats,
            to_csv,
        ):
            self.assertTrue(callable(function))

    def test_render_svg_returns_str(self) -> None:
        self.assertIsInstance(render_svg(generate_grid(5, 1), 20, False), str)

    def test_slope_stats_type(self) -> None:
        stats = slope_stats(generate_grid(5, 1))
        self.assertIsInstance(stats, SlopeStats)
        self.assertIsInstance(stats.total, int)

    def test_grid_property_types(self) -> None:
        grid = generate_grid(5, 1)
        self.assertIsInstance(grid.rows, int)
        self.assertIsInstance(grid.cols, int)
        self.assertIsInstance(grid.min, float)
        self.assertIsInstance(grid.max, float)

    def test_parse_and_render_roundtrip(self) -> None:
        grid = generate_grid(7, 2)
        restored = parse_grid(to_csv(grid))
        self.assertEqual(grid, restored)


if __name__ == "__main__":
    unittest.main()

