#!/usr/bin/env python3
"""Prepare an image for the 64x32 HUB75 panel.

Downscales with nearest-neighbour (keeps pixel art crisp), lifts dark tones so
they survive the panel's CIE1931 gamma (otherwise near-black pixels are simply
off), desaturates the darkest tones so outlines stay neutral, and flattens
transparency onto black.

    python3 tools/prep_image.py images/dog-2.png images/dog-2-32.png --size 32x32

Requires Pillow (already installed with ESPHome).
"""
import argparse
import colorsys

from PIL import Image


def lift(im: Image.Image, floor: float, gamma: float) -> Image.Image:
    im = im.copy()
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a < 128:
                px[x, y] = (0, 0, 0, 0)
                continue
            h, s, v0 = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            v = floor + (1 - floor) * (v0 ** gamma)
            s *= min(1.0, v0 * 2.5)  # darkest tones go neutral rather than vivid
            r2, g2, b2 = colorsys.hsv_to_rgb(h, s, v)
            px[x, y] = (round(r2 * 255), round(g2 * 255), round(b2 * 255), 255)
    return im


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--size", default="32x32", help="WxH, default 32x32")
    ap.add_argument("--floor", type=float, default=0.22, help="minimum brightness for opaque pixels")
    ap.add_argument("--gamma", type=float, default=0.8, help="<1 brightens shadows")
    args = ap.parse_args()

    w, h = (int(n) for n in args.size.lower().split("x"))
    src = Image.open(args.src).convert("RGBA")
    out = lift(src, args.floor, args.gamma).resize((w, h), Image.NEAREST)
    bg = Image.new("RGBA", out.size, (0, 0, 0, 255))
    bg.alpha_composite(out)
    bg.convert("RGB").save(args.dst)
    print(f"{args.src} -> {args.dst} ({w}x{h})")


if __name__ == "__main__":
    main()
