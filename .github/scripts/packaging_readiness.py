#!/usr/bin/env python3
"""Detect the previously missing group toolbar and DataGrid header bands."""
import argparse
import json
from pathlib import Path
import struct
import zlib


def read_rgb_png(path):
    data = Path(path).read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Expected a PNG screenshot')
    offset, compressed = 8, bytearray()
    width = height = None
    while offset < len(data):
        length = struct.unpack('>I', data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        if kind == b'IHDR':
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
            if (depth, color, compression, filtering, interlace) != (8, 2, 0, 0, 0):
                raise ValueError('Expected the RGB format emitted by the task X11 helper')
        elif kind == b'IDAT':
            compressed.extend(payload)
        offset += length + 12
    decoded = zlib.decompress(compressed)
    stride = width * 3 + 1
    if len(decoded) != stride * height:
        raise ValueError('Unexpected screenshot byte length')
    rows = []
    for y in range(height):
        line = decoded[y * stride:(y + 1) * stride]
        if line[0] != 0:
            raise ValueError('Expected the unfiltered rows emitted by the task X11 helper')
        rows.append(line[1:])
    return width, height, rows


def band_statistics(rows, screen_width, screen_height, x, y, width, height):
    if x < 0 or y < 0 or x + width > screen_width or y + height > screen_height:
        raise ValueError('The complete target band is outside the screenshot')
    nonwhite = 0
    for row in rows[y:y + height]:
        values = row[x * 3:(x + width) * 3]
        nonwhite += sum(min(values[index:index + 3]) < 245 for index in range(0, len(values), 3))
    return {'root_rect': [x, y, width, height], 'pixel_count': width * height,
            'nonwhite_pixels': nonwhite, 'nonwhite_fraction': nonwhite / (width * height)}


def assess(path, geometry):
    width, height, rows = read_rgb_png(path)
    x, y, window_width = geometry['x'], geometry['y'], geometry['width']
    toolbar = band_statistics(rows, width, height, x, y + 54, window_width, 50)
    header = band_statistics(rows, width, height, x, y + 104, window_width, 36)
    threshold = max(500, window_width // 2)
    return {'screenshot': str(Path(path)), 'window_geometry': geometry,
        'toolbar_band': toolbar, 'header_band': header, 'threshold_nonwhite_pixels': threshold,
        'toolbar_and_headers_present': toolbar['nonwhite_pixels'] >= threshold
            and header['nonwhite_pixels'] >= threshold,
        'scope': 'Measures the known missing toolbar/header bands. Exit-dialog pixels are outside both bands; manual full-window review remains required.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('screenshot', type=Path)
    parser.add_argument('--result', type=Path, required=True,
        help='Result JSON containing the exact owned main_window geometry')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = json.loads(args.result.read_text())
    assessment = assess(args.screenshot, result['main_window']['geometry'])
    text = json.dumps(assessment, indent=2)
    if args.output:
        args.output.write_text(text + '\n')
    print(text)
    return 0 if assessment['toolbar_and_headers_present'] else 1


if __name__ == '__main__':
    raise SystemExit(main())