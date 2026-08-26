from __future__ import annotations

import ctypes
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.environ.get("MOJO_OPENPYXL_LIB") or os.path.join(
    ROOT, "dist", "libmojo-openpyxl.so"
)
I = ctypes.c_int64
_SIGNATURES = {
    "mox_escape_size": ([I, I], I),
    "mox_escape": ([I, I, I, I], I),
    "mox_escape_sized": ([I, I, I, I, I], I),
    "mox_coordinates": ([I, I, I, I, I, I], I),
    "mox_coordinates_packed": ([I, I, I, I, I], I),
    "mox_write_sheet": ([I, I, I, I, I, I, I, I, I], I),
}
_handle = None
_COORDINATE_PARALLEL_THRESHOLD = 32_768
_COORDINATE_WORKERS = min(os.cpu_count() or 1, 8)
_coordinate_pool = None
_bytes_address = ctypes.pythonapi.PyBytes_AsString
_bytes_address.argtypes = [ctypes.py_object]
_bytes_address.restype = ctypes.c_void_p


def build(force: bool = False) -> str:
    source = os.path.join(ROOT, "src", "openpyxl.mojo")
    if not force and os.path.exists(LIB) and os.path.getmtime(LIB) >= os.path.getmtime(source):
        return LIB
    proc = subprocess.run(
        ["bash", os.path.join(ROOT, "build", "build.sh")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if proc.returncode or not os.path.exists(LIB):
        raise RuntimeError((proc.stderr or proc.stdout).strip()[:4000])
    return LIB


def lib() -> ctypes.CDLL:
    global _handle
    if _handle is None:
        _handle = ctypes.CDLL(build())
        for name, (argtypes, restype) in _SIGNATURES.items():
            fn = getattr(_handle, name)
            fn.argtypes = argtypes
            fn.restype = restype
    return _handle


def addr(value) -> int:
    if isinstance(value, np.ndarray):
        address = value.ctypes.data
        if value.size and not address:
            raise ValueError("non-empty NumPy array has a null data pointer")
        return address
    if isinstance(value, bytes):
        return _bytes_address(value)
    return ctypes.addressof(ctypes.c_char.from_buffer(value))


def _coordinate_executor():
    global _coordinate_pool
    if _coordinate_pool is None:
        _coordinate_pool = ThreadPoolExecutor(max_workers=_COORDINATE_WORKERS)
    return _coordinate_pool


def escape(value: str) -> str:
    raw = value.encode("utf-8")
    if not raw:
        return ""
    size = lib().mox_escape_size(addr(raw), len(raw))
    if size < 0:
        raise RuntimeError("native XML escape rejected its input")
    result = bytearray(size)
    used = lib().mox_escape_sized(
        addr(raw), len(raw), addr(result), len(result), size
    )
    if used != size:
        raise RuntimeError("internal XML escape size mismatch")
    return result.decode("utf-8")


def coordinates(rows, columns) -> list[str]:
    raw_rows = np.asarray(rows)
    raw_columns = np.asarray(columns)
    if raw_rows.dtype.kind not in "iu" or raw_columns.dtype.kind not in "iu":
        raise TypeError("rows and columns must contain integers")
    r = np.ascontiguousarray(raw_rows, dtype=np.int64)
    c = np.ascontiguousarray(raw_columns, dtype=np.int64)
    if r.shape != c.shape:
        raise ValueError("rows and columns must have the same shape")
    if r.ndim != 1:
        raise ValueError("rows and columns must be one-dimensional")
    if not r.size:
        return []
    stride = 11
    result = bytearray(r.size * stride)
    native = lib().mox_coordinates_packed
    if r.size < _COORDINATE_PARALLEL_THRESHOLD or _COORDINATE_WORKERS == 1:
        chunks = [(0, native(addr(r), addr(c), r.size, addr(result), len(result)))]
    else:
        workers = min(_COORDINATE_WORKERS, r.size)

        def convert(worker):
            start = worker * r.size // workers
            stop = (worker + 1) * r.size // workers
            count = stop - start
            return native(
                addr(r) + start * r.itemsize,
                addr(c) + start * c.itemsize,
                count,
                addr(result) + start * stride,
                count * stride,
            )

        used = list(_coordinate_executor().map(convert, range(workers)))
        chunks = [
            (worker * r.size // workers * stride, used[worker])
            for worker in range(workers)
        ]
    if any(used == -3 for _, used in chunks):
        raise ValueError("row or column values are outside Excel's supported range")
    if any(used < 0 for _, used in chunks):
        raise RuntimeError(f"native coordinate conversion failed ({chunks})")
    if len(chunks) == 1:
        del result[chunks[0][1] :]
        packed = result
    else:
        view = memoryview(result)
        packed = b"".join(view[start : start + used] for start, used in chunks)
    return packed.decode("ascii").splitlines()


def write_sheet(cells) -> bytes:
    n = len(cells)
    if not n:
        return b""
    rows = np.fromiter((c.row for c in cells), dtype=np.int64, count=n)
    columns = np.fromiter((c.column for c in cells), dtype=np.int64, count=n)
    if np.any((rows < 1) | (rows > 1_048_576)):
        raise ValueError("cell rows must be between 1 and 1048576")
    if np.any((columns < 1) | (columns > 18_278)):
        raise ValueError("cell columns must be between 1 and 18278")
    kinds = np.empty(n, dtype=np.uint8)
    offsets = np.empty(n + 1, dtype=np.int64)
    chunks: list[bytes] = []
    total = 0
    offsets[0] = 0
    for i, cell in enumerate(cells):
        kind, raw = cell._encoded()
        kinds[i] = kind
        chunks.append(raw)
        total += len(raw)
        offsets[i + 1] = total
    values = bytearray(b"".join(chunks))
    if not values:
        values = bytearray(1)
    capacity = total * 6 + n * 128 + len({c.row for c in cells}) * 32
    result = bytearray(max(capacity, 1))
    used = lib().mox_write_sheet(
        addr(rows),
        addr(columns),
        addr(kinds),
        addr(offsets),
        addr(values),
        total,
        n,
        addr(result),
        len(result),
    )
    if used < 0:
        raise RuntimeError(f"native worksheet serialization failed ({used})")
    if used > len(result):
        raise RuntimeError("native worksheet serializer returned an invalid length")
    return bytes(result[:used])
