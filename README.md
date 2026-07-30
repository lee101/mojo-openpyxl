# mojo-openpyxl

`mojo-openpyxl` is a standalone XLSX reader and writer with an
[openpyxl](https://openpyxl.readthedocs.io/) shaped Python API and a Mojo
worksheet serializer. It is intended for data-oriented workbooks where cell
I/O dominates: the ZIP container and workbook relationships are managed in
Python, while Mojo emits cell references, escapes XML text, and serializes a
whole worksheet body in one native call.

```python
from mojo_openpyxl import Workbook, load_workbook

workbook = Workbook()
sheet = workbook.active
sheet.title = "Results"
sheet.append(["sample", "score", "accepted"])
sheet.append(["A&B", 98.5, True])
sheet["D2"] = "=B2/100"
workbook.save("results.xlsx")

loaded = load_workbook("results.xlsx", data_only=False)
print(list(loaded["Results"].values))
```

## Covered subset

The public names and signatures follow openpyxl 3.1 for the covered API:

| area | implemented |
| --- | --- |
| workbook | `Workbook`, `load_workbook`, `save`, `close`, `active`, `sheetnames`, `worksheets`, `create_sheet`, `remove`, `move_sheet`, name/index lookup |
| worksheet | `cell`, A1 access and assignment, rectangular range access, `append`, `iter_rows`, `iter_cols`, `rows`, `columns`, `values`, dimensions |
| cell values | strings, integers, floats, booleans, formulas, Excel error values, `date`, `datetime`, and `time` |
| XLSX reading | inline strings, numbers, booleans, formulas, `data_only=True`, ISO and style-based dates, and multiple worksheets |
| coordinate utilities | `get_column_letter`, `column_index_from_string`, `coordinate_from_string`, `coordinate_to_tuple`, `range_boundaries`, `range_to_tuple`, `absolute_coordinate`, `rows_from_range`, `cols_from_range` |

The test suite compares these behaviors in both directions: openpyxl reads
files produced here, this package reads files produced by openpyxl, and utility
results are checked directly against upstream.

This is deliberately not the whole openpyxl object model. Styles, merged
cells, comments, hyperlinks, tables, charts, images, conditional formatting,
data validation, named ranges, macros, and rich text are not preserved.
Streaming `read_only=True`, rich text, and VBA preservation raise
`NotImplementedError`; `write_only=True` accepts the upstream constructor
signature but currently retains cells until save. Formula expressions are
stored and loaded, but neither this library nor openpyxl calculates them.

## Install and run

The pixi environment includes the pinned Mojo nightly, Python, NumPy,
openpyxl for parity testing, and pytest.

```bash
pixi install
pixi run build
pixi run test
pixi run bench
```

`pixi run build` creates `dist/libmojo-openpyxl.so`. Imports also rebuild the
library when the Mojo source is newer. Set `MOJO_OPENPYXL_LIB` to an existing
shared library when packaging or deploying without the compiler.

## Performance

Measured with `pixi run bench` on this machine immediately before publication:
x86-64, Linux 6.8.0-136-generic, Python 3.13.14, and openpyxl 3.1.5. Times are
the best of three runs. The coordinate comparison includes conversion back to
Python strings, and the XML reference is CPython's C-level `html.escape`.

| case | mojo-openpyxl | openpyxl/reference | result |
| --- | ---: | ---: | ---: |
| 200k cell coordinates | 104.3 ms | 106.7 ms | 1.02x faster |
| XML escape 12.5 MB | 144.3 ms | 119.4 ms | 0.83x slower |
| save dense 20k x 10 | 790.4 ms | 2162.6 ms | 2.74x faster |
| save text/formulas 30k x 4 | 363.9 ms | 1837.0 ms | 5.05x faster |
| load dense 20k x 10 | 1521.4 ms | 2192.4 ms | 1.44x faster |

Worksheet writing remains the largest win: one Mojo call emits all row and cell
tags, coordinates, escaped strings, numbers, booleans, formulas, and dates.
SIMD handles escape sizing and plain-byte copies, large coordinate batches use
thresholded CPU parallelism, and the reader avoids per-cell namespace queries
and general coordinate parsing.

No GPU path is included. The hot kernels are branch-heavy text formatting,
escaping, and XML parsing with low arithmetic intensity, well below the level
where host/device transfers are justified.

## How it works

Python owns all objects and memory. Before save, cells are sorted in row-major
order and represented by contiguous NumPy `int64` row, column, and offset
arrays, a `uint8` type array, and one packed UTF-8 value buffer. Their addresses
cross `ctypes` as C `int64` values. Mojo rebuilds
`UnsafePointer[..., AnyOrigin[mut=True]]` views, writes the `<sheetData>` body
into a caller-owned byte buffer, and returns the used byte count. No object
pointer crosses the ABI and Mojo performs no allocation. Calls are synchronous,
so Python retains every backing buffer for the full native call. The wrapper
requires contiguous arrays with exact dtypes, rejects narrowing and invalid
coordinates, and passes destination and value-buffer lengths; Mojo validates
those lengths, offsets, pointers, and output capacity before writing.

The remaining Open Packaging Convention parts are small XML documents produced
in Python and assembled with `zipfile`. Reading reverses this process using the
standard library XML parser, including workbook relationships, shared strings,
cell types, styles needed to identify dates, and Excel epoch handling.

## License

MIT
