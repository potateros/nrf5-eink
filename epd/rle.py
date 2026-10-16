"""RLE codec matching EPD-nRF5 firmware (html/js/rle.js)."""


def compress(data: bytes, max_literal: int = 128) -> bytes:
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        run = 1
        while i + run < n and run < 130 and data[i + run] == data[i]:
            run += 1
        if run >= 3:
            out += bytes((0x80 | (run - 3), data[i]))
            i += run
            continue
        start = i
        while i < n and i - start < max_literal:
            if i + 2 < n and data[i] == data[i + 1] == data[i + 2]:
                break
            i += 1
        out.append(i - start - 1)
        out += data[start:i]
    return bytes(out)


def chunks(data: bytes, max_chunk: int) -> list[bytes]:
    """Compress, then split at code boundaries so each chunk decodes standalone."""
    stream = compress(data, min(max_chunk - 1, 128))
    result, start, i = [], 0, 0
    while i < len(stream):
        code_len = 2 if stream[i] & 0x80 else stream[i] + 2
        if i - start + code_len > max_chunk and i > start:
            result.append(stream[start:i])
            start = i
        i += code_len
    if i > start:
        result.append(stream[start:i])
    return result


def decompress(data: bytes) -> bytes:
    out, i = bytearray(), 0
    while i < len(data):
        c = data[i]
        if c & 0x80:
            out += bytes([data[i + 1]]) * ((c & 0x7F) + 3)
            i += 2
        else:
            out += data[i + 1 : i + 2 + c]
            i += c + 2
    return bytes(out)
