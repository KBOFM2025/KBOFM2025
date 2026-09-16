"""연습경기에서 사용하는 구장 사진의 형식과 최소 해상도를 검사한다."""

from __future__ import annotations

import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STADIUM_ROOT = ROOT / "image" / "Stadium"
ASSETS = {
    "kia.jpg", "samsung.jpg", "jamsil.jpg", "kt.jpg", "ssg.jpg",
    "lotte.jpg", "hanwha.jpg", "nc.jpg", "kiwoom.jpg",
}


def jpeg_size(path):
    with path.open("rb") as source:
        if source.read(2) != b"\xff\xd8":
            raise ValueError(f"JPEG 형식이 아닙니다: {path}")
        while True:
            marker_start = source.read(1)
            if not marker_start:
                break
            if marker_start != b"\xff":
                continue
            marker = source.read(1)
            while marker == b"\xff":
                marker = source.read(1)
            if marker in {b"\xd8", b"\xd9"}:
                continue
            length_data = source.read(2)
            if len(length_data) != 2:
                break
            length = struct.unpack(">H", length_data)[0]
            if marker in {
                bytes([value]) for value in (
                    0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                    0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
                )
            }:
                precision_height_width = source.read(5)
                if len(precision_height_width) != 5:
                    break
                _precision, height, width = struct.unpack(">BHH", precision_height_width)
                return width, height
            source.seek(length - 2, 1)
    raise ValueError(f"JPEG 크기를 읽을 수 없습니다: {path}")


def main():
    report = {}
    for name in sorted(ASSETS):
        path = STADIUM_ROOT / name
        if not path.exists():
            raise AssertionError(f"구장 사진 누락: {name}")
        width, height = jpeg_size(path)
        if width < 1920 or height < 800:
            raise AssertionError(f"구장 사진 해상도 부족: {name} {width}x{height}")
        report[name] = f"{width}x{height}"
    for name, dimensions in report.items():
        print(f"{name:14} {dimensions}")


if __name__ == "__main__":
    main()
