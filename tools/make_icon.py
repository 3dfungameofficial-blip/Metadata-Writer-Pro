"""Generate assets/icon.png + assets/icon.ico (Pillow only). Run: python tools/make_icon.py"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

SIZE = 256
img = Image.new("RGBA", (SIZE, SIZE), (24, 28, 38, 255))
d = ImageDraw.Draw(img)
# Rounded tag/card glyph: accent square + tag lines (original artwork, no brand copying)
d.rounded_rectangle([28, 52, 228, 204], radius=36, fill=(79, 124, 255, 255))
d.rounded_rectangle([28, 52, 228, 104], radius=36, fill=(99, 143, 255, 255))
d.rectangle([28, 76, 228, 104], fill=(99, 143, 255, 255))
d.ellipse([52, 128, 84, 160], fill=(24, 28, 38, 255))
for i, w in enumerate((120, 92, 104)):
    y = 132 + i * 20
    d.rounded_rectangle([96, y, 96 + w, y + 10], radius=5, fill=(255, 255, 255, 235))

img.save(ASSETS / "icon.png")
img.save(ASSETS / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"wrote {ASSETS / 'icon.png'} and {ASSETS / 'icon.ico'}")
