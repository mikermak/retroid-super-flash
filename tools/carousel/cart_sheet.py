# Overview sheet of all cart types (front, side, variant, blank) from library-db renders.
# Usage: python tools/carousel/cart_sheet.py <out.png>
import os, sys
from PIL import Image, ImageDraw, ImageFont
R = r"C:/Users/aruur/Documents/Retroid/firmware/library-db/renders"
OUT = sys.argv[1]
rows = [
    ("GBA", "Model: Vxcl (Sketchfab, CC-BY 4.0)", ["gba_84406", "gba_84411"], "blank_gba"),
    ("Game Boy", "Model: Val Turcea (Sketchfab, CC-BY 4.0)", ["gb_2976", "gb_2967"], "blank_gb"),
    ("Game Boy Color", "Model: Val Turcea (Sketchfab, CC-BY 4.0)", ["gbc_82375", "gbc_82606"], "blank_gbc"),
    ("NES", "Model: Anette Rana (Sketchfab, CC-BY 4.0)", ["nes_1245", "nes_1250"], "blank_nes"),
]
cols = ["Voorkant", "Schuin (zijkant in carrousel)", "Andere kleur / variant", "Leeg (geen label)"]
CW, CH, LW, HH = 470, 330, 300, 60
W, H = LW + CW * len(cols), HH + CH * len(rows)
img = Image.new("RGB", (W, H), (38, 40, 46))
d = ImageDraw.Draw(img)
fb = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 30)
fs = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 19)
fh = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 20)
for i, c in enumerate(cols):
    d.text((LW + i * CW + CW // 2, HH // 2), c, font=fh, fill=(220, 220, 225), anchor="mm")
def paste(path, cx, cy):
    if not os.path.exists(path):
        d.text((cx, cy), "ontbreekt", font=fs, fill=(200, 80, 80), anchor="mm"); return
    im = Image.open(path).convert("RGBA")
    img.paste(im, (cx - im.width // 2, cy - im.height // 2), im)
for r, (name, model, games, blank) in enumerate(rows):
    y0 = HH + r * CH
    if r % 2 == 0:
        d.rectangle([0, y0, W, y0 + CH], fill=(46, 48, 55))
    d.text((24, y0 + CH // 2 - 22), name, font=fb, fill=(255, 255, 255), anchor="lm")
    d.text((24, y0 + CH // 2 + 18), model, font=fs, fill=(170, 175, 185), anchor="lm")
    cy = y0 + CH // 2
    paste(f"{R}/{games[0]}/F.png", LW + CW // 2, cy)
    paste(f"{R}/{games[0]}/L.png", LW + CW + CW // 2, cy)
    paste(f"{R}/{games[1]}/F.png", LW + 2 * CW + CW // 2, cy)
    paste(f"{R}/{blank}/F.png", LW + 3 * CW + CW // 2, cy)
img.save(OUT)
print(OUT, img.size)
