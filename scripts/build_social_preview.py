"""Build the 1280x640 GitHub social preview / Open Graph image, without new simulation.

The artwork is the published Butterfly Lab poster (docs/chaos/poster.png), cropped to
its trajectory sculpture and faded into the dark background under the headline copy.
"""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 1280, 640
MARGIN = 48
BACKGROUND = "#09121b"
PANEL = "#111c27"
LAVENDER, ORANGE, MINT = "#c1b1ff", "#ffca85", "#79dfc3"
WHITE, GREY, MONO_GREY = "#f1f5ef", "#a7bac6", "#98aeba"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"docs/showcase/social.png")
    parser.add_argument("--poster", type=Path, default=ROOT/"docs/chaos/poster.png")
    parser.add_argument("--fonts", type=Path, default=Path("/usr/share/fonts/truetype/dejavu"))
    args = parser.parse_args()
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    def font(name, size):
        return ImageFont.truetype(str(args.fonts/name), size)

    def fitted(name, size, text, max_width, minimum=10):
        """Return the largest font at or below `size` whose rendering of `text` fits."""
        while size > minimum:
            candidate = font(name, size)
            right = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), text, font=candidate)[2]
            if right <= max_width:
                return candidate
            size -= 1
        return font(name, minimum)

    # --- Artwork: crop the poster to its sculpture, fit it to the left panel, fade its right edge.
    art_width = int(WIDTH*0.55)  # 704
    fade_start = 0.55            # fraction of the art width where the fade begins
    with Image.open(args.poster) as poster:
        if poster.size != (900, 640):
            raise ValueError("Poster layout changed; update the sculpture crop")
        plate = poster.convert("RGB")
    # Blank the viewer chrome (time readout, axis caption, orbit buttons) that sits
    # inside the sculpture's bounding box, using the poster's own background color.
    night = plate.getpixel((880, 300))
    plate_draw = ImageDraw.Draw(plate)
    for box in ((90, 98, 280, 152), (90, 568, 480, 592), (655, 555, 815, 598)):
        plate_draw.rectangle(box, fill=night)
    sculpture = plate.crop((200, 66, 900, 600))
    art = ImageOps.fit(sculpture, (art_width, HEIGHT), Image.Resampling.LANCZOS, centering=(0.3, 0.5))
    mask = Image.new("L", (art_width, HEIGHT), 255)
    mask_draw = ImageDraw.Draw(mask)
    fade_x0 = int(art_width*fade_start)
    for x in range(fade_x0, art_width):
        t = (x-fade_x0)/(art_width-fade_x0)
        alpha = int(255*(1-t)**1.6)
        mask_draw.line((x, 0, x, HEIGHT), fill=alpha)
    # Soft vertical vignette so the crop's top/bottom edges do not read as a hard frame.
    for y in range(0, 40):
        t = y/40
        column = mask.crop((0, y, art_width, y+1)).point(lambda v, t=t: int(v*t))
        mask.paste(column, (0, y))
        column = mask.crop((0, HEIGHT-1-y, art_width, HEIGHT-y)).point(lambda v, t=t: int(v*t))
        mask.paste(column, (0, HEIGHT-1-y))

    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    boxes = {}

    def text(name, xy, string, font, fill):
        draw.text(xy, string, font=font, fill=fill)
        boxes[name] = draw.textbbox(xy, string, font=font)
    # Faint grid, echoing the README showcase, kept to the right-hand copy area.
    for y in range(0, HEIGHT, 32):
        draw.line((art_width//2, y, WIDTH, y), fill="#0e1a24")
    for x in range(art_width//2, WIDTH, 32):
        draw.line((x, 0, x, HEIGHT), fill="#0e1a24")
    image.paste(art, (0, 0), mask)
    draw = ImageDraw.Draw(image)

    # --- Copy block on the right.
    text_x = 668
    text_right = WIDTH-MARGIN
    max_text_width = text_right-text_x

    eyebrow_font = fitted("DejaVuSansMono.ttf", 15, "ROBOT REEL · PHYSICAL AI REPLAY LAB", max_text_width)
    headline_lines = ("Give Physical AI", "a replay button.")
    headline_font = fitted("DejaVuSans-Bold.ttf", 56, max(headline_lines, key=len), max_text_width)
    subline = "Real rollouts. Inspectable films. Editable 3D scenes."
    subline_font = fitted("DejaVuSans.ttf", 22, subline, max_text_width)
    chip_size = 15
    url_font = font("DejaVuSansMono.ttf", 14)

    y = 168
    draw.rounded_rectangle((text_x, y+3, text_x+30, y+7), radius=2, fill=MINT)
    text("eyebrow", (text_x+42, y-4), "ROBOT REEL · PHYSICAL AI REPLAY LAB", eyebrow_font, MINT)
    y += 46
    for index, line in enumerate(headline_lines):
        text(f"headline{index}", (text_x-4, y), line, headline_font, WHITE)
        y += int(headline_font.size*1.14)
    y += 18
    text("subline", (text_x, y), subline, subline_font, GREY)
    subline_bottom = boxes["subline"][3]

    # --- Chips, bottom right, laid out right-to-left so they hug the margin.
    chips = (("SmolVLA · MuJoCo", LAVENDER), ("Newton → OpenUSD", ORANGE), ("MCP → Blender", MINT))
    chip_h = 36
    chip_pad = 16
    chip_gap = 12
    chip_y1 = HEIGHT-MARGIN
    chip_y0 = chip_y1-chip_h
    while True:
        chip_font = font("DejaVuSans-Bold.ttf", chip_size)
        widths = []
        for label, _ in chips:
            left, _, right, _ = draw.textbbox((0, 0), label, font=chip_font)
            widths.append(right-left+2*chip_pad)
        total = sum(widths)+chip_gap*(len(chips)-1)
        if total <= max_text_width or chip_size <= 11:
            break
        chip_size -= 1
    if total > max_text_width:
        raise ValueError(f"Chips overflow the copy column by {total-max_text_width}px")
    x = text_right-total
    for (label, color), w in zip(chips, widths):
        draw.rounded_rectangle((x, chip_y0, x+w, chip_y1), radius=10, fill=PANEL, outline=color, width=2)
        left, top, right, bottom = draw.textbbox((0, 0), label, font=chip_font)
        text(f"chip {label}", (x+chip_pad-left, chip_y0+(chip_h-(bottom-top))//2-top), label, chip_font, color)
        x += w+chip_gap
    if subline_bottom+24 > chip_y0:
        raise ValueError("Copy block runs into the chips")

    # --- Footer URL, bottom left, over the faded poster floor.
    url = "noteflowai.github.io/robot-reel"
    left, top, right, bottom = draw.textbbox((0, 0), url, font=url_font)
    url_y = HEIGHT-MARGIN-(bottom-top)-top
    text("url", (MARGIN, url_y), url, url_font, MONO_GREY)
    if MARGIN+right-left+24 > text_right-total:
        raise ValueError("Footer URL collides with the chips")
    for name, (left, top, right, bottom) in boxes.items():
        if min(left, top, WIDTH-right, HEIGHT-bottom) < MARGIN:
            raise ValueError(f"{name!r} is closer than {MARGIN}px to the edge: {(left, top, right, bottom)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, optimize=True)
    print(f"Social preview {WIDTH}x{HEIGHT} from {args.poster.relative_to(ROOT)}: {args.output}")
    print(f"{args.output.stat().st_size} bytes")


if __name__ == "__main__":
    main()
