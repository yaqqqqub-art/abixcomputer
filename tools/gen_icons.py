#!/usr/bin/env python3
"""Generates the original ABIX app icons (frontend/icons/*.svg) and converts the two icons you supplied (PNG).
Re-run to regenerate:  python3 tools/gen_icons.py
Official brand icons are not bundled. To use one, replace frontend/icons/<id>.svg (or the PNG and its name in backend/abix_launch.py)."""
import os
from PIL import Image
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "icons")
os.makedirs(OUT, exist_ok=True)


def svg(body, defs=""):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">'
            + ("<defs>%s</defs>" % defs if defs else "") + body + "</svg>")


def tile(fill, extra=""):
    return '<rect x="3" y="3" width="58" height="58" rx="14" fill="%s"/>%s' % (fill, extra)


def grad(i, a, b):
    return '<linearGradient id="%s" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient>' % (i, a, b)


A = "M20 44 32 18l12 26h-6l-2.4-5.6h-7.2L26 44z M30 34h4l-2-4.8z"
I = {}
I["terminal"] = svg(tile("#1f2430") + '<path d="M16 22l12 10-12 10" fill="none" stroke="#5be49b" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><path d="M32 44h16" stroke="#fff" stroke-width="5" stroke-linecap="round"/>')
I["notepad"] = svg('<rect x="10" y="9" width="44" height="48" rx="7" fill="#2ea8e6"/><rect x="10" y="50" width="44" height="7" rx="3.5" fill="#c58a4a"/>'
                   '<g fill="#fff"><rect x="18" y="22" width="28" height="4" rx="2"/><rect x="18" y="31" width="28" height="4" rx="2"/><rect x="18" y="40" width="18" height="4" rx="2"/></g>'
                   '<g fill="#1b6fa8"><circle cx="20" cy="9" r="3.5"/><circle cx="32" cy="9" r="3.5"/><circle cx="44" cy="9" r="3.5"/></g>')
I["calculator"] = svg(tile("#2b3040") + '<rect x="14" y="12" width="36" height="12" rx="3" fill="#a8f0c6"/>'
                      '<g fill="#e9edf5"><rect x="14" y="30" width="9" height="8" rx="2"/><rect x="27" y="30" width="9" height="8" rx="2"/><rect x="40" y="30" width="9" height="8" rx="2"/>'
                      '<rect x="14" y="42" width="9" height="8" rx="2"/><rect x="27" y="42" width="9" height="8" rx="2"/></g><rect x="40" y="42" width="9" height="8" rx="2" fill="#ff9f43"/>')
I["archive"] = svg(tile("#f3b73a") + '<rect x="14" y="16" width="36" height="32" rx="4" fill="#fff3cf"/><rect x="29" y="16" width="6" height="32" fill="#8a6a1c"/>'
                   '<g fill="#fff3cf"><rect x="29" y="20" width="6" height="3"/><rect x="29" y="26" width="6" height="3"/><rect x="29" y="32" width="6" height="3"/></g><rect x="27" y="38" width="10" height="8" rx="2" fill="#8a6a1c"/>')
I["task-manager"] = svg(tile("#232a38") + '<path d="M12 44l10-12 8 6 10-16 12 10" fill="none" stroke="#5be49b" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M12 52h40" stroke="#4b566b" stroke-width="3" stroke-linecap="round"/>')
I["system-monitor"] = svg(tile("#232a38") + '<g fill="#4cc2ff"><rect x="14" y="30" width="7" height="20" rx="2"/><rect x="25" y="20" width="7" height="30" rx="2"/><rect x="36" y="26" width="7" height="24" rx="2"/></g><rect x="47" y="14" width="5" height="36" rx="2" fill="#ff9f43"/>')
I["settings"] = svg('<g fill="#7d8797"><circle cx="32" cy="32" r="20"/>' + "".join('<rect x="27" y="4" width="10" height="12" rx="3" transform="rotate(%d 32 32)"/>' % a for a in range(0, 360, 45)) + '</g><circle cx="32" cy="32" r="12" fill="#e6ebf3"/><circle cx="32" cy="32" r="7" fill="#1f6fd0"/>')
I["abix-browser"] = svg(tile("url(#g)") + '<circle cx="32" cy="32" r="16" fill="none" stroke="#fff" stroke-width="3"/><ellipse cx="32" cy="32" rx="7" ry="16" fill="none" stroke="#fff" stroke-width="3"/><path d="M16 32h32M19 23h26M19 41h26" stroke="#fff" stroke-width="2.4" fill="none"/>', grad("g", "#4cc2ff", "#7a5cff"))
I["chrome"] = svg('<circle cx="32" cy="32" r="28" fill="#e94235"/><path d="M32 32 L56.2 46 A28 28 0 0 1 7.8 46 Z" fill="#34a853"/><path d="M32 32 L56.2 46 A28 28 0 0 0 56.2 18 L32 4 Z" fill="#fbbc05" transform="rotate(0)"/>'
                  '<path d="M32 32 L32 4 A28 28 0 0 1 56.2 18 Z" fill="#e94235"/><circle cx="32" cy="32" r="12" fill="#fff"/><circle cx="32" cy="32" r="9" fill="#4285f4"/>')
I["firefox"] = svg('<circle cx="32" cy="32" r="27" fill="url(#f)"/><path d="M16 38c2 10 14 16 24 10 8-5 10-14 6-22 1 6-2 11-8 12-8 1-12-5-10-12-6 2-14 6-12 12z" fill="#ffd36b" opacity=".9"/>', grad("f", "#ff9a1f", "#a021d6"))
I["edge"] = svg('<circle cx="32" cy="32" r="27" fill="url(#e)"/><path d="M14 36c0-12 10-20 21-18 9 2 14 9 12 17H27c1 6 8 8 14 4l5 6c-12 9-32 4-32-9z" fill="#fff" opacity=".92"/>', grad("e", "#2fd0a0", "#1068d8"))
I["whatsapp"] = svg(tile("#25d366") + '<path d="M32 13a19 19 0 0 0-16.4 28.6L13 51l9.700-2.5A19 19 0 1 0 32 13z" fill="#fff"/><path d="M25 24c-1 2-1 5 2 9s7 6 10 6c2 0 3-2 3-3l-4-2-2 2c-3-1-6-4-7-7l2-2-2-5z" fill="#25d366"/>')
I["imo"] = svg(tile("#1a8cff") + '<path d="M32 14c-10 0-18 7-18 16 0 5 2 9 6 12l-2 8 9-4c2 .5 3 .5 5 .5 10 0 18-7 18-16S42 14 32 14z" fill="#fff"/><text x="32" y="36" font-family="Arial,Helvetica,sans-serif" font-size="14" font-weight="700" text-anchor="middle" fill="#1a8cff">imo</text>')
I["telegram"] = svg('<circle cx="32" cy="32" r="28" fill="#2aabee"/><path d="M14 31l33-13c1.500-.6 3 .4 2.500 2.800L44 45c-.4 1.800-1.500 2.200-3 1.400l-8-6-4 4c-.5.500-.8.800-1.600.8l.6-8.200 15-13.600c.7-.6-.2-.9-1-.4L22.500 35 15 32.600c-1.600-.5-1.600-1.600.4-2.600z" fill="#fff"/>')
I["premiere"] = svg(tile("#00005b") + '<text x="32" y="41" font-family="Arial,Helvetica,sans-serif" font-size="26" font-weight="700" text-anchor="middle" fill="#9999ff">Pr</text>')
I["aftereffects"] = svg(tile("#00005b") + '<text x="32" y="41" font-family="Arial,Helvetica,sans-serif" font-size="26" font-weight="700" text-anchor="middle" fill="#d291ff">Ae</text>')
I["gimp"] = svg(tile("#6b5e4a") + '<ellipse cx="32" cy="33" rx="17" ry="15" fill="#e8dcc4"/><circle cx="26" cy="29" r="3" fill="#3b3226"/><circle cx="38" cy="29" r="3" fill="#3b3226"/><path d="M24 40c4 4 12 4 16 0" stroke="#3b3226" stroke-width="3" fill="none" stroke-linecap="round"/>')
I["inkscape"] = svg(tile("#1b1b1f") + '<path d="M32 12 44 36 32 52 20 36z" fill="#fff"/><circle cx="32" cy="34" r="4" fill="#1b1b1f"/><path d="M32 12v18" stroke="#1b1b1f" stroke-width="3"/>')
I["krita"] = svg(tile("#17a89b") + '<path d="M18 46c4-2 6-8 10-14l16-16 6 6-16 16c-6 4-12 6-16 8z" fill="#fff"/><circle cx="19" cy="47" r="4" fill="#ff9f43"/>')
I["audacity"] = svg(tile("#1f2430") + '<path d="M14 34v-4a18 18 0 0 1 36 0v4" fill="none" stroke="#4cc2ff" stroke-width="4"/><rect x="11" y="32" width="8" height="14" rx="3" fill="#4cc2ff"/><rect x="45" y="32" width="8" height="14" rx="3" fill="#4cc2ff"/><path d="M24 40v-4M29 44V32M34 42V34M39 40v-4" stroke="#ff9f43" stroke-width="3" stroke-linecap="round"/>')
I["kdenlive"] = svg(tile("#2b6fd6") + '<rect x="12" y="16" width="40" height="32" rx="4" fill="#fff"/><g fill="#2b6fd6"><rect x="15" y="19" width="4" height="4"/><rect x="15" y="27" width="4" height="4"/><rect x="15" y="35" width="4" height="4"/><rect x="45" y="19" width="4" height="4"/><rect x="45" y="27" width="4" height="4"/><rect x="45" y="35" width="4" height="4"/></g><path d="M28 24l12 8-12 8z" fill="#2b6fd6"/>')
I["vscode"] = svg(tile("#1e1e1e") + '<path d="M44 12 26 29 17 22l-4 3 9 8-9 8 4 3 9-7 18 17 7-3V15z" fill="#2aa5f0"/><path d="M44 22v20L33 32z" fill="#1e1e1e"/>')
for k, v in I.items():
    open(os.path.join(OUT, k + ".svg"), "w", encoding="utf-8").write(v)

UP = "/mnt/user-data/uploads/"
for src, name in (("1794540324393_image.png", "file-manager.png"), ("1794540440349_image.png", "screenshot.png")):
    p = UP + src
    if os.path.exists(p):
        im = Image.open(p).convert("RGBA")
        bg = Image.new("RGBA", im.size, (0, 0, 0, 0))
        px = im.load()
        w, h = im.size
        if px[0, 0][:3] in ((255, 255, 255),) or sum(px[0, 0][:3]) > 740:      # near-white background -> transparent
            for y in range(h):
                for x in range(w):
                    r, g, b, a = px[x, y]
                    if r > 245 and g > 245 and b > 245:
                        px[x, y] = (r, g, b, 0)
        im.resize((128, 128), Image.LANCZOS).save(os.path.join(OUT, name), optimize=True)
print("icons written:", len(os.listdir(OUT)))
