"""Hot XLSX text kernels exposed through one C ABI compilation unit."""

from std.algorithm import parallelize
from std.gpu.host import DeviceContext
from std.sys.info import simd_width_of as simdwidthof

comptime BPtr = UnsafePointer[UInt8, AnyOrigin[mut=True]]
comptime IPtr = UnsafePointer[Int64, AnyOrigin[mut=True]]


def escaped_size(src: BPtr, start: Int, stop: Int) -> Int:
    var size = 0
    comptime W = simdwidthof[DType.float64]()
    var i = start
    var vector_stop = start + (stop - start) // W * W
    while i < vector_stop:
        var chars = src.load[width=W](i)
        var extra = chars.eq(SIMD[DType.uint8, W](38)).select(
            SIMD[DType.uint8, W](4), SIMD[DType.uint8, W](0)
        )
        extra += chars.eq(SIMD[DType.uint8, W](60)).select(
            SIMD[DType.uint8, W](3), SIMD[DType.uint8, W](0)
        )
        extra += chars.eq(SIMD[DType.uint8, W](62)).select(
            SIMD[DType.uint8, W](3), SIMD[DType.uint8, W](0)
        )
        extra += chars.eq(SIMD[DType.uint8, W](34)).select(
            SIMD[DType.uint8, W](5), SIMD[DType.uint8, W](0)
        )
        extra += chars.eq(SIMD[DType.uint8, W](39)).select(
            SIMD[DType.uint8, W](5), SIMD[DType.uint8, W](0)
        )
        size += W + Int(extra.reduce_add())
        i += W
    while i < stop:
        var c = src[i]
        if c == 38:
            size += 5
        elif c == 60 or c == 62:
            size += 4
        elif c == 34:
            size += 6
        elif c == 39:
            size += 6
        else:
            size += 1
        i += 1
    return size


def put_escape(src: BPtr, start: Int, stop: Int, dst: BPtr, pos: Int) -> Int:
    var p = pos
    comptime W = simdwidthof[DType.float64]()
    var i = start
    var vector_stop = start + (stop - start) // W * W
    while i < vector_stop:
        var chars = src.load[width=W](i)
        var special = (
            chars.eq(SIMD[DType.uint8, W](38))
            | chars.eq(SIMD[DType.uint8, W](60))
            | chars.eq(SIMD[DType.uint8, W](62))
            | chars.eq(SIMD[DType.uint8, W](34))
            | chars.eq(SIMD[DType.uint8, W](39))
        )
        if not Bool(special.reduce_or()):
            dst.store(p, chars)
            p += W
            i += W
            continue
        var lane_stop = i + W
        while i < lane_stop:
            var c = src[i]
            if c == 38:
                dst[p] = 38
                dst[p + 1] = 97
                dst[p + 2] = 109
                dst[p + 3] = 112
                dst[p + 4] = 59
                p += 5
            elif c == 60:
                dst[p] = 38
                dst[p + 1] = 108
                dst[p + 2] = 116
                dst[p + 3] = 59
                p += 4
            elif c == 62:
                dst[p] = 38
                dst[p + 1] = 103
                dst[p + 2] = 116
                dst[p + 3] = 59
                p += 4
            elif c == 34:
                dst[p] = 38
                dst[p + 1] = 113
                dst[p + 2] = 117
                dst[p + 3] = 111
                dst[p + 4] = 116
                dst[p + 5] = 59
                p += 6
            elif c == 39:
                dst[p] = 38
                dst[p + 1] = 97
                dst[p + 2] = 112
                dst[p + 3] = 111
                dst[p + 4] = 115
                dst[p + 5] = 59
                p += 6
            else:
                dst[p] = c
                p += 1
            i += 1
    while i < stop:
        var c = src[i]
        if c == 38:
            dst[p] = 38
            dst[p + 1] = 97
            dst[p + 2] = 109
            dst[p + 3] = 112
            dst[p + 4] = 59
            p += 5
        elif c == 60:
            dst[p] = 38
            dst[p + 1] = 108
            dst[p + 2] = 116
            dst[p + 3] = 59
            p += 4
        elif c == 62:
            dst[p] = 38
            dst[p + 1] = 103
            dst[p + 2] = 116
            dst[p + 3] = 59
            p += 4
        elif c == 34:
            dst[p] = 38
            dst[p + 1] = 113
            dst[p + 2] = 117
            dst[p + 3] = 111
            dst[p + 4] = 116
            dst[p + 5] = 59
            p += 6
        elif c == 39:
            dst[p] = 38
            dst[p + 1] = 97
            dst[p + 2] = 112
            dst[p + 3] = 111
            dst[p + 4] = 115
            dst[p + 5] = 59
            p += 6
        else:
            dst[p] = c
            p += 1
        i += 1
    return p


def put_byte(dst: BPtr, pos: Int, value: Int) -> Int:
    dst[pos] = UInt8(value)
    return pos + 1


def put_uint(dst: BPtr, pos: Int, value: Int) -> Int:
    var divisor = 1
    var x = value
    while x >= 10:
        divisor *= 10
        x //= 10
    var p = pos
    var remaining = value
    while divisor > 0:
        dst[p] = UInt8(48 + remaining // divisor)
        remaining %= divisor
        divisor //= 10
        p += 1
    return p


def column_width(value: Int) -> Int:
    var width = 0
    var x = value
    while x > 0:
        width += 1
        x = (x - 1) // 26
    return width


def put_column(dst: BPtr, pos: Int, value: Int) -> Int:
    var width = column_width(value)
    var p = pos + width
    var x = value
    while x > 0:
        x -= 1
        p -= 1
        dst[p] = UInt8(65 + x % 26)
        x //= 26
    return pos + width


def put_coord(dst: BPtr, pos: Int, row: Int, column: Int) -> Int:
    return put_uint(dst, put_column(dst, pos, column), row)


def put_text(dst: BPtr, pos: Int, text: String) -> Int:
    var p = pos
    var src = text.unsafe_ptr()
    for i in range(text.byte_length()):
        dst[p] = src[i]
        p += 1
    return p


def boundary_space(src: BPtr, start: Int, stop: Int) -> Bool:
    if start == stop:
        return False
    var first = src[start]
    var last = src[stop - 1]
    return first == 32 or first == 9 or first == 10 or first == 13 or last == 32 or last == 9 or last == 10 or last == 13


@export("mox_escape_size")
def mox_escape_size(src_addr: Int, n: Int) abi("C") -> Int:
    if n < 0 or (n > 0 and src_addr == 0):
        return -1
    if n == 0:
        return 0
    var src = BPtr(unsafe_from_address=src_addr)
    return escaped_size(src, 0, n)


@export("mox_escape")
def mox_escape(src_addr: Int, n: Int, dst_addr: Int, dst_capacity: Int) abi("C") -> Int:
    if n < 0 or dst_capacity < 0 or (n > 0 and src_addr == 0):
        return -1
    if n == 0:
        return 0
    if dst_addr == 0:
        return -1
    var src = BPtr(unsafe_from_address=src_addr)
    var required = escaped_size(src, 0, n)
    if required > dst_capacity:
        return -2
    var dst = BPtr(unsafe_from_address=dst_addr)
    return put_escape(src, 0, n, dst, 0)


@export("mox_coordinates")
def mox_coordinates(
    rows_addr: Int,
    columns_addr: Int,
    n: Int,
    dst_addr: Int,
    dst_capacity: Int,
    stride: Int,
) abi("C") -> Int:
    if n < 0 or stride < 1 or dst_capacity < 0:
        return -1
    if n == 0:
        return 0
    if rows_addr == 0 or columns_addr == 0 or dst_addr == 0:
        return -1
    if n > dst_capacity // stride:
        return -2
    var rows = IPtr(unsafe_from_address=rows_addr)
    var columns = IPtr(unsafe_from_address=columns_addr)
    var dst = BPtr(unsafe_from_address=dst_addr)
    for i in range(n):
        var row = Int(rows[i])
        var column = Int(columns[i])
        if row < 1 or row > 1048576 or column < 1 or column > 18278:
            return -3
        if column_width(column) + 7 > stride:
            return -2

    if n < 32768:
        for i in range(n):
            var start = i * stride
            var p = put_coord(dst, start, Int(rows[i]), Int(columns[i]))
            dst[p] = 0
    else:
        comptime CHUNK = 4096
        var chunks = (n + CHUNK - 1) // CHUNK

        def write_chunk(chunk: Int) {var rows, var columns, var dst, var stride, var n}:
            var first = chunk * CHUNK
            var stop = min(first + CHUNK, n)
            for i in range(first, stop):
                var start = i * stride
                var p = put_coord(dst, start, Int(rows[i]), Int(columns[i]))
                dst[p] = 0

        try:
            var ctx = DeviceContext(api="cpu")
            parallelize(write_chunk, chunks, ctx=ctx)
        except:
            for i in range(n):
                var start = i * stride
                var p = put_coord(dst, start, Int(rows[i]), Int(columns[i]))
                dst[p] = 0
    return 0


@export("mox_write_sheet")
def mox_write_sheet(
    rows_addr: Int,
    columns_addr: Int,
    kinds_addr: Int,
    offsets_addr: Int,
    values_addr: Int,
    values_length: Int,
    n: Int,
    dst_addr: Int,
    dst_capacity: Int,
) abi("C") -> Int:
    if n < 0 or values_length < 0 or dst_capacity < 0:
        return -1
    if n == 0:
        return 0
    if (
        rows_addr == 0
        or columns_addr == 0
        or kinds_addr == 0
        or offsets_addr == 0
        or values_addr == 0
        or dst_addr == 0
    ):
        return -1
    var rows = IPtr(unsafe_from_address=rows_addr)
    var columns = IPtr(unsafe_from_address=columns_addr)
    var kinds = BPtr(unsafe_from_address=kinds_addr)
    var offsets = IPtr(unsafe_from_address=offsets_addr)
    var values = BPtr(unsafe_from_address=values_addr)
    var dst = BPtr(unsafe_from_address=dst_addr)
    if Int(offsets[0]) != 0 or Int(offsets[n]) != values_length:
        return -3
    for i in range(n):
        var row = Int(rows[i])
        var column = Int(columns[i])
        var start = Int(offsets[i])
        var stop = Int(offsets[i + 1])
        if row < 1 or row > 1048576 or column < 1 or column > 18278:
            return -3
        if kinds[i] < 1 or kinds[i] > 6 or start < 0 or stop < start or stop > values_length:
            return -3
    # This conservative bound is the same allocation contract used by Python:
    # six bytes per input byte plus fixed XML overhead for every cell and row.
    if values_length > (dst_capacity - n * 128) // 6:
        return -2
    var p = 0
    var active_row = 0
    for i in range(n):
        var row = Int(rows[i])
        var column = Int(columns[i])
        if row != active_row:
            if active_row != 0:
                p = put_text(dst, p, "</row>")
            p = put_text(dst, p, "<row r=\"")
            p = put_uint(dst, p, row)
            p = put_text(dst, p, "\">")
            active_row = row
        p = put_text(dst, p, "<c r=\"")
        p = put_coord(dst, p, row, column)
        var kind = kinds[i]
        var start = Int(offsets[i])
        var stop = Int(offsets[i + 1])
        if kind == 1:
            p = put_text(dst, p, "\" t=\"inlineStr\"><is><t")
            if boundary_space(values, start, stop):
                p = put_text(dst, p, " xml:space=\"preserve\"")
            p = put_byte(dst, p, 62)
            p = put_escape(values, start, stop, dst, p)
            p = put_text(dst, p, "</t></is></c>")
        elif kind == 2:
            p = put_text(dst, p, "\"><v>")
            for j in range(start, stop):
                dst[p] = values[j]
                p += 1
            p = put_text(dst, p, "</v></c>")
        elif kind == 3:
            p = put_text(dst, p, "\" t=\"b\"><v>")
            for j in range(start, stop):
                dst[p] = values[j]
                p += 1
            p = put_text(dst, p, "</v></c>")
        elif kind == 4:
            p = put_text(dst, p, "\"><f>")
            p = put_escape(values, start, stop, dst, p)
            p = put_text(dst, p, "</f></c>")
        elif kind == 5:
            p = put_text(dst, p, "\" t=\"d\"><v>")
            for j in range(start, stop):
                dst[p] = values[j]
                p += 1
            p = put_text(dst, p, "</v></c>")
        else:
            p = put_text(dst, p, "\" t=\"e\"><v>")
            for j in range(start, stop):
                dst[p] = values[j]
                p += 1
            p = put_text(dst, p, "</v></c>")
    if active_row != 0:
        p = put_text(dst, p, "</row>")
    return p
