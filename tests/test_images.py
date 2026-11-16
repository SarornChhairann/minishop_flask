import io

import pytest
from PIL import Image

from app.services.images import ImageError, process_image


def test_png_becomes_two_capped_jpegs(png_bytes):
    original, thumb = process_image(png_bytes((2400, 1800), "RGBA"))
    big, small = Image.open(io.BytesIO(original)), Image.open(io.BytesIO(thumb))
    assert big.format == small.format == "JPEG"
    assert big.mode == "RGB"
    assert max(big.size) == 1600 and max(small.size) == 480
    assert big.size[0] / big.size[1] == pytest.approx(2400 / 1800, rel=0.01)


def test_small_image_is_not_upscaled(png_bytes):
    original, _ = process_image(png_bytes((300, 200), "RGB"))
    assert Image.open(io.BytesIO(original)).size == (300, 200)


def test_text_file_is_rejected():
    with pytest.raises(ImageError):
        process_image(b"hello, this is not an image")


def test_oversize_is_rejected():
    with pytest.raises(ImageError):
        process_image(b"\0" * (5 * 1024 * 1024 + 1))
