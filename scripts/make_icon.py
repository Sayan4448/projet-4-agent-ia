"""Generate assets/app.ico with Pillow (run once from the venv)."""
from pathlib import Path

from PIL import Image, ImageDraw


def draw(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256  # scale factor from the 256 design

    # rounded dark background
    d.rounded_rectangle([8 * s, 8 * s, 248 * s, 248 * s], radius=48 * s, fill=(23, 26, 33, 255))

    # head
    d.rounded_rectangle([56 * s, 78 * s, 200 * s, 196 * s], radius=28 * s, fill=(108, 140, 255, 255))
    # antenna
    d.line([128 * s, 78 * s, 128 * s, 48 * s], fill=(108, 140, 255, 255), width=int(8 * s))
    d.ellipse([116 * s, 32 * s, 140 * s, 56 * s], fill=(123, 216, 143, 255))
    # eyes
    d.ellipse([84 * s, 112 * s, 120 * s, 148 * s], fill=(15, 17, 21, 255))
    d.ellipse([136 * s, 112 * s, 172 * s, 148 * s], fill=(15, 17, 21, 255))
    d.ellipse([94 * s, 122 * s, 106 * s, 134 * s], fill=(232, 234, 240, 255))
    d.ellipse([146 * s, 122 * s, 158 * s, 134 * s], fill=(232, 234, 240, 255))
    # mouth
    d.rounded_rectangle([96 * s, 162 * s, 160 * s, 172 * s], radius=5 * s, fill=(15, 17, 21, 255))
    return img


def main() -> None:
    out = Path("assets/app.ico")
    out.parent.mkdir(parents=True, exist_ok=True)
    base = draw(256)
    base.save(out, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"icon written: {out}")


if __name__ == "__main__":
    main()
