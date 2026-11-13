#!/usr/bin/env python3
"""Abix wallpaper generator. Original procedural art (no third-party images, no trademarks).
Usage: python3 assets/tools/gen_wallpapers.py   (needs Pillow + numpy; only for the project author, not needed at runtime)"""
import os, numpy as np
from PIL import Image

W, H = 2560, 1440
OUT = os.path.join(os.path.dirname(__file__), "..", "wallpapers")
os.makedirs(OUT, exist_ok=True)
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
xx /= W; yy /= H
rng = np.random.default_rng(7)

def blob(cx, cy, sx, sy, rot=0.0):
    x, y = xx - cx, (yy - cy) * (H / W)
    c, s = np.cos(rot), np.sin(rot)
    xr, yr = x * c + y * s, -x * s + y * c
    return np.exp(-((xr / sx) ** 2 + (yr / sy) ** 2))

def compose(base, layers):
    img = np.zeros((H, W, 3), np.float32) + np.array(base, np.float32)
    for (col, strength, b) in layers:
        a = (b * strength)[..., None]
        img = img * (1 - a) + np.array(col, np.float32) * a
    img += rng.normal(0, 1.2, img.shape).astype(np.float32)   # tiny noise: avoids colour banding
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))

def save(img, name):
    img.save(os.path.join(OUT, name), quality=90, optimize=True)
    print("wrote", name)

save(compose((232, 240, 252), [((120, 170, 255), .9, blob(.30, .55, .35, .30, .5)),
                               ((190, 140, 255), .8, blob(.72, .35, .30, .25, -.4)),
                               ((255, 170, 210), .7, blob(.60, .85, .35, .15, .2)),
                               ((255, 255, 255), .6, blob(.45, .40, .20, .12))]), "abix-bloom-light.jpg")
save(compose((8, 14, 32), [((20, 70, 190), .95, blob(.30, .55, .35, .30, .5)),
                           ((110, 50, 200), .85, blob(.72, .35, .30, .25, -.4)),
                           ((190, 50, 140), .6, blob(.62, .88, .30, .12, .2)),
                           ((60, 140, 255), .4, blob(.45, .42, .15, .10))]), "abix-bloom-dark.jpg")
band = np.sin((xx * 3.0 + yy * 1.2) * np.pi) * .5 + .5
save(compose((6, 18, 24), [((20, 200, 150), .75, blob(.5, .5, .60, .10, -.35) * (.5 + .5 * band)),
                           ((40, 120, 230), .6, blob(.25, .25, .35, .12, -.35)),
                           ((140, 90, 230), .5, blob(.80, .75, .30, .10, -.35))]), "abix-aurora.jpg")
grad = yy[..., None]
dusk = (np.array([40, 30, 90]) * (1 - grad) + np.array([255, 130, 100]) * grad).astype(np.float32)
img = dusk + 0
sun = blob(.5, .78, .13, .13)[..., None]
img = img * (1 - sun * .9) + np.array([255, 220, 160]) * sun * .9
img += rng.normal(0, 1.2, img.shape)
save(Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)), "abix-dusk.jpg")
wave = np.zeros_like(xx)
for i, (amp, f, ph) in enumerate([(.04, 3, 0), (.03, 5, 1.3), (.02, 8, 2.1)]):
    wave += amp * np.sin(xx * f * np.pi + ph + yy * 2)
t = np.clip(yy + wave, 0, 1)[..., None]
ocean = np.array([10, 40, 90]) * (1 - t) + np.array([40, 190, 220]) * t
ocean += rng.normal(0, 1.2, ocean.shape)
save(Image.fromarray(np.clip(ocean, 0, 255).astype(np.uint8)), "abix-ocean.jpg")
save(compose((24, 26, 30), [((70, 74, 84), .8, blob(.30, .30, .45, .30, .4)),
                            ((50, 54, 66), .7, blob(.80, .80, .40, .25, -.3))]), "abix-graphite.jpg")
