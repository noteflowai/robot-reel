"""Compose the Space preview from four actual lab captures; retain their hashes."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.pages import digest


def main():
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    entries = (
        ("microduck-lab", "MICRODUCK MOTION", "14 joints / recorded targets + response"),
        ("stress", "SMOLVLA STRESS", "30 trials / every outcome retained"),
        ("cloth", "GPU CLOTH", "42,471 vertex samples / OpenUSD"),
        ("chaos", "BUTTERFLY LAB", "12 Newton worlds / original poses"),
    )
    image = Image.new("RGB", (1280, 840), "#09151d")
    draw = ImageDraw.Draw(image)
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    draw.text((30, 20), "ROBOT REEL", font=ImageFont.truetype(bold, 35), fill="#edf4ef")
    draw.text((31, 69), "Four Physical AI labs. Keep the evidence behind the motion.",
              font=ImageFont.truetype(font, 20), fill="#a9bdc8")
    sources = {}
    for i, (lab, title, caption) in enumerate(entries):
        source = ROOT/"docs"/lab/"poster.png"
        sources[source.relative_to(ROOT).as_posix()] = digest(source)
        x, y = 30+(i % 2)*630, 120+(i//2)*345
        panel = ImageOps.contain(Image.open(source).convert("RGB"), (590, 252), Image.Resampling.LANCZOS)
        draw.rounded_rectangle((x, y, x+590, y+319), radius=10, fill="#10242b", outline="#34515a")
        image.paste(panel, (x+(590-panel.width)//2, y+(252-panel.height)//2))
        draw.text((x+13, y+263), title, font=ImageFont.truetype(bold, 17), fill="#79dfc3")
        draw.text((x+13, y+289), caption, font=ImageFont.truetype(font, 14), fill="#a9bdc8")
    draw.text((30, 814), "Recorded simulation / simplified schematic / upstream media terms apply",
              font=ImageFont.truetype(font, 12), fill="#a9bdc8")
    target = ROOT/"huggingface/thumbnail.png"
    image.save(target, optimize=True)
    (ROOT/"huggingface/thumbnail.json").write_text(json.dumps({
        "source_posters_sha256": sources, "thumbnail_sha256": digest(target),
        "composition": "Four unaltered lab captures, fit inside labeled panels.",
        "media_notice": "NOTICE.txt",
    }, indent=2)+"\n")


if __name__ == "__main__":
    main()
