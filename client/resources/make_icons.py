"""Draw the Wavelane logo and write the application icon files.

The logo is three wavy lines. The same geometry is used by qml/Logo.qml, so the
mark inside the app and the icon in the taskbar are one drawing.

Run from anywhere with the project's Python (it needs Pillow):

    python client/resources/make_icons.py

Writes wavelane.ico (for the executable) and wavelane-<size>.png (for the
window icon) next to this script. Lines are drawn without a background, so the
icon sits on whatever the taskbar looks like.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent

# Top to bottom. Must match the colours in qml/Logo.qml.
COLOURS = [(0x27, 0xC9, 0xE8), (0x8A, 0x5C, 0xFF), (0x2F, 0x63, 0xE6)]
# Unit-square geometry shared with the QML canvas.
ROWS = (0.32, 0.50, 0.68)
X_START, X_END = 0.08, 0.92
CONTROL_X = (0.30, 0.62)
CONTROL_DY = 0.17

SIZES = (16, 24, 32, 48, 64, 128, 256)
SUPERSAMPLE = 8


def bezier(p0, p1, p2, p3, steps=900):
    points = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
        points.append((x, y))
    return points


def stroke_width(size: int) -> float:
    """Relative stroke width. Small icons need heavier lines to stay legible."""
    if size <= 24:
        return 0.13
    if size <= 48:
        return 0.105
    return 0.088


def draw(size: int) -> Image.Image:
    big = size * SUPERSAMPLE
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    painter = ImageDraw.Draw(image)
    width = stroke_width(size) * big

    for row, colour in zip(ROWS, COLOURS, strict=True):
        points = bezier(
            (X_START, row),
            (CONTROL_X[0], row - CONTROL_DY),
            (CONTROL_X[1], row + CONTROL_DY),
            (X_END, row),
        )
        # Stamp a dot at every sample instead of joining segments: PIL's joins
        # leave small spikes on the outside of a curve, a row of dots does not.
        radius = width / 2
        for x, y in points:
            cx, cy = x * big, y * big
            painter.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                            fill=colour + (255,))

    return image.resize((size, size), Image.LANCZOS)


def draw_discord_asset(size: int = 1024) -> Image.Image:
    """The logo on a dark tile, for Discord's Rich Presence art assets.

    Discord shows the image as a square tile and wants at least 512 px, so
    unlike the icon it needs a background and plenty of margin.
    """
    tile = Image.new("RGBA", (size, size), (12, 13, 17, 255))
    mark = draw(size * 3 // 5)
    offset = (size - mark.width) // 2
    tile.alpha_composite(mark, (offset, offset))
    return tile


def main() -> None:
    images = {size: draw(size) for size in SIZES}
    for size, image in images.items():
        image.save(HERE / f"wavelane-{size}.png")

    # Pillow builds the ICO's smaller images from the largest one unless given
    # explicit sizes, so draw each size natively and let it pick them up.
    images[256].save(
        HERE / "wavelane.ico",
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=[images[s] for s in SIZES if s != 256],
    )
    draw_discord_asset().save(HERE / "wavelane-discord.png")
    print("wrote wavelane.ico and", ", ".join(f"wavelane-{s}.png" for s in SIZES))


if __name__ == "__main__":
    main()
