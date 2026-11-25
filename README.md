# contour

[![CI](https://github.com/eastyou/contour/actions/workflows/ci.yml/badge.svg)](https://github.com/eastyou/contour/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)

contour 是一个面向初中地理教学的等高线地形图读图工具。它根据高程网格生成等高线地形图，判读山顶、鞍部、山脊、山谷、陡坡、缓坡与平地，统计坡度分布，并输出可直接打印的 A4 练习纸。全部功能只依赖 Python 标准库。

## 特性

- 生成 5×5 到 25×25 的方形高程网格，网格包含两座山峰及其间的鞍部，同一随机种子结果可复现。
- 使用 marching squares 算法从高程网格提取等高线并输出 SVG，图中包含图名、等高距、比例说明与三角形指北针。
- 可通过 `--labels` 在等高线上标注高程数值。
- 判读任意格点的地形部位，同时输出该点高程与四邻域高程。
- 统计最陡、最缓、平均坡度，并按 `<15 度`、`15~25 度`、`25~35 度`、`>35 度` 分级计数。
- 生成 A4 练习纸，包含判读地形部位、计算相对高度、比较坡度三类题目，可选参考答案页。
- 生成演示页，同时展示彩色高程网格图、等高线地形图与地形部位说明。
- 仅使用标准库，兼容 Python 3.9 及以上版本。

## 安装

无需安装即可在仓库根目录运行：

```bash
python -m contour --help
```

如需安装命令行入口：

```bash
python -m pip install .
contour --help
```

## 使用

生成高程网格 CSV：

```bash
python -m contour grid -o grid.csv --size 11 --seed 7
```

```text
已生成 11 x 11 网格，高程范围 122.5 ~ 431.1 米，输出：grid.csv
```

CSV 首行为列名 `C0,C1,...`，之后每行是一行格点的高程。行号由北向南递增，列号由西向东递增。

绘制等高线地形图：

```bash
python -m contour draw grid.csv -o contour.svg --interval 20 --labels
```

```text
已绘制等高线地形图，等高距 20.0，输出：contour.svg
```

判读地形部位：

```bash
python -m contour feature grid.csv --x 3 --y 4
```

```text
地形部位：山脊
高程：430.1 米
坐标：x=3, y=4
四邻域：
  北 (x=3, y=3) 高程 420.0 米
  南 (x=3, y=5) 高程 397.2 米
  西 (x=2, y=4) 高程 391.5 米
  东 (x=4, y=4) 高程 431.1 米
```

统计坡度：

```bash
python -m contour slope grid.csv
```

```text
最陡坡度：36.09 度
最缓坡度：0.46 度
平均坡度：18.82 度
分级统计（共 220 条坡线）：
  <15 度：78
  15~25 度：77
  25~35 度：60
  >35 度：5
```

生成练习纸与演示页：

```bash
python -m contour sheet -o sheet.html --count 6 --answers
python -m contour demo -o demo.html
```

```text
已生成练习纸：sheet.html（题目 6 道，含参考答案）
已生成演示页：demo.html
```

### 参数

| 子命令 | 参数 | 必填 | 说明 |
| --- | --- | --- | --- |
| `grid` | `-o, --output` | 是 | 输出的 CSV 文件路径 |
| `grid` | `--size` | 否 | 网格边长，范围 5~25，默认 11 |
| `grid` | `--seed` | 否 | 随机种子，默认 0 |
| `draw` | `grid_file` | 是 | 高程网格 CSV 文件 |
| `draw` | `-o, --output` | 是 | 输出的 SVG 文件路径 |
| `draw` | `--interval` | 是 | 等高距，必须大于 0 |
| `draw` | `--labels` | 否 | 在等高线上标注高程 |
| `feature` | `grid_file` | 是 | 高程网格 CSV 文件 |
| `feature` | `--x` | 是 | 列坐标，从 0 开始 |
| `feature` | `--y` | 是 | 行坐标，从 0 开始 |
| `slope` | `grid_file` | 是 | 高程网格 CSV 文件 |
| `sheet` | `-o, --output` | 是 | 输出的 HTML 文件路径 |
| `sheet` | `--count` | 否 | 题目数量，范围 1~20，默认 6 |
| `sheet` | `--answers` | 否 | 附加参考答案页 |
| `demo` | `-o, --output` | 是 | 输出的 HTML 文件路径 |

### 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 命令执行成功 |
| 2 | 参数或输入数据有误，标准错误输出以「错误：」开头 |

## 地形部位判定规则

等高线图层级从高于最低点的下一个等高距倍数开始，超出高程范围的层级会被跳过。

- 山顶：该点高程不低于其四邻域，且至少有一个邻点低于该点。
- 鞍部：南北两侧都高于该点、同时东西两侧都低于该点；或东西两侧都高于该点、同时南北两侧都低于该点。
- 山脊：沿某一方向（南北或东西）两侧均低于该点。
- 山谷：沿某一方向（南北或东西）两侧均高于该点。
- 陡坡 / 缓坡：以上均不成立时，用邻域最大高差与水平距离计算坡度角，不小于 25 度判为陡坡，否则为缓坡。
- 平地：四邻域高程与该点完全相同。

高程单位为米，相邻格点的水平距离按 100 米计，坡度角等于 `arctan(高差 / 100)`。

## 作为库使用

```python
from contour import Grid, classify_point, parse_grid, render_svg, slope_stats

grid = parse_grid(open("grid.csv", encoding="utf-8").read())
print(grid.rows, grid.cols, grid.min, grid.max)
print(classify_point(grid, 3, 4))

stats = slope_stats(grid)
print(stats.steepest, stats.gentlest, stats.average)

svg = render_svg(grid, interval=20, labels=True)
```

主要 API：

| 名称 | 说明 |
| --- | --- |
| `Grid(cells)` | 高程网格，提供 `rows`、`cols`、`min`、`max` 属性 |
| `parse_grid(text)` | 把 CSV 文本解析为 `Grid` |
| `marching_squares(grid, level)` | 提取一条等值线，返回线段列表 |
| `render_svg(grid, interval, labels)` | 渲染等高线地形图 SVG |
| `classify_point(grid, x, y)` | 判读地形部位 |
| `slope_stats(grid)` | 返回坡度统计 `SlopeStats` |
| `render_sheet(grid, count, answers)` | 渲染 A4 练习纸 HTML |

输入不合法时会抛出带中文说明的 `ValueError`，例如空文本、只有表头、行列不齐、非数值、NaN、Inf、网格小于 2×2、坐标越界、等高距不大于 0。

## 开发与测试

```bash
python -m unittest discover -s tests -v
```

测试共 190 个用例，覆盖正常流程、边界条件与命令行退出码，全部基于标准库 `unittest`，无需安装任何第三方依赖。CI 在 Ubuntu 上使用 Python 3.9、3.10、3.11、3.12、3.13 运行同一套测试。

## License

[MIT](LICENSE) © 2026 eastyou
