#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""博客封面自动合成 v3
版式 style: left(左对齐) / top(顶部宽排) / bottom(底部式) / center(居中式) / poster(大字报+底部深遮罩白字) / poster-white(顶部白遮罩黑字) / 兼容旧 align 值
风格包 accent: 衬线斜体强调词 + 行尾年份胶囊 + 次要句降级
tags: 关键词胶囊行(传入则渲染)"""
from PIL import Image, ImageDraw, ImageFont
import sys, re, os, subprocess

# 字体按角色解析:依次尝试各平台常见路径,都没有则从官方仓库下载到缓存(与底图缓存同目录)。
# 缓存命中后不再联网。Liberation Sans 与 Arial 度量兼容,跨平台渲染结果基本一致。
_FONT_CACHE = "/tmp/pd-cover-assets/fonts"
_NOTO = "https://raw.githubusercontent.com/notofonts/notofonts.github.io/main/fonts"
_NOTO_CJK = "https://raw.githubusercontent.com/notofonts/noto-cjk/main"
_FONTS = {
    "bold_cjk": (["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                  "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
                  "C:/Windows/Fonts/msyhbd.ttc",
                  "/System/Library/Fonts/PingFang.ttc",
                  "/System/Library/Fonts/Hiragino Sans GB.ttc"],
                 "NotoSansSC-Bold.otf", f"{_NOTO_CJK}/Sans/SubsetOTF/SC/NotoSansSC-Bold.otf"),
    "reg_cjk":  (["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                  "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
                  "C:/Windows/Fonts/msyh.ttc",
                  "/System/Library/Fonts/PingFang.ttc",
                  "/System/Library/Fonts/Hiragino Sans GB.ttc"],
                 "NotoSansSC-Regular.otf", f"{_NOTO_CJK}/Sans/SubsetOTF/SC/NotoSansSC-Regular.otf"),
    "bold_lat": (["/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                  "/usr/share/fonts/liberation-sans/LiberationSans-Bold.ttf",
                  "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                  "C:/Windows/Fonts/arialbd.ttf"],
                 "NotoSans-Bold.ttf", f"{_NOTO}/NotoSans/hinted/ttf/NotoSans-Bold.ttf"),
    "reg_lat":  (["/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                  "/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf",
                  "/System/Library/Fonts/Supplemental/Arial.ttf",
                  "C:/Windows/Fonts/arial.ttf"],
                 "NotoSans-Regular.ttf", f"{_NOTO}/NotoSans/hinted/ttf/NotoSans-Regular.ttf"),
    "serif_it": (["/usr/share/fonts/truetype/liberation2/LiberationSerif-BoldItalic.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf",
                  "/usr/share/fonts/liberation-serif/LiberationSerif-BoldItalic.ttf",
                  "/System/Library/Fonts/Supplemental/Times New Roman Bold Italic.ttf",
                  "C:/Windows/Fonts/timesbi.ttf"],
                 "NotoSerif-BoldItalic.ttf", f"{_NOTO}/NotoSerif/hinted/ttf/NotoSerif-BoldItalic.ttf"),
}
_resolved = {}

def F(role):
    if role not in _resolved:
        candidates, dl_name, dl_url = _FONTS[role]
        env = os.environ.get(f"PD_FONT_{role.upper()}")
        found = env if env and os.path.exists(env) else next(
            (p for p in candidates if os.path.exists(p)), None)
        if not found:
            os.makedirs(_FONT_CACHE, exist_ok=True)
            found = os.path.join(_FONT_CACHE, dl_name)
            if not os.path.exists(found):
                subprocess.run(["curl", "-sL", "--fail", "-o", found, dl_url],
                               check=True, timeout=300)
        _resolved[role] = found
    return _resolved[role]

BOLD_CJK, REG_CJK = "bold_cjk", "reg_cjk"
BOLD_LAT, REG_LAT = "bold_lat", "reg_lat"
SERIF_IT = "serif_it"

def is_cjk(t): return any('一' <= c <= '鿿' for c in t)
OPEN = "（(《「【"; CLOSE = "）)》」】，。、：；！？"

def _hex(c):
    c = c.lstrip("#"); return tuple(int(c[i:i+2], 16) for i in (0, 2, 4))
def _mix(a, b, t): return tuple(int(a[i]*(1-t)+b[i]*t) for i in range(3))
import colorsys
def _boost(c, sat=1.0, val=1.0):
    h, s_, v = colorsys.rgb_to_hsv(*[x/255 for x in c])
    r, g, b = colorsys.hsv_to_rgb(h, min(1, s_*sat), min(1, v*val))
    return (int(r*255), int(g*255), int(b*255))

def wrap(d, text, font, max_w):
    if not is_cjk(text):
        lines, cur = [], ""
        for w in text.split():
            t = (cur + " " + w).strip()
            if d.textlength(t, font=font) <= max_w: cur = t
            else:
                if cur: lines.append(cur)
                cur = w
        if cur: lines.append(cur)
        return lines
    lines, cur = [], ""
    for ch in text:
        if d.textlength(cur + ch, font=font) <= max_w or (ch in CLOSE and cur): cur += ch
        else:
            if cur and cur[-1] in OPEN: lines.append(cur[:-1]); cur = cur[-1] + ch
            else: lines.append(cur); cur = ch
    if cur: lines.append(cur)
    return [l for l in lines if l]

def _split_title(title):
    """主句/次句拆分：问号或冒号后的部分、尾部括号 → 次要行(小号)"""
    secondary = []
    m = re.search(r"\s*(\([^)]*\))\s*$", title)
    if m: secondary.insert(0, m.group(1)); title = title[:m.start()]
    m = re.match(r"^(.{8,}?[?？:：])\s+(.{6,})$", title)
    if m: title = m.group(1); secondary.insert(0, m.group(2))
    return title.strip(), secondary

def _tokens(primary, accent_word):
    words = primary.split(); toks, i = [], 0
    while i < len(words):
        w = words[i]
        if re.fullmatch(r"20\d\d[?？,.]*", w) and toks and toks[-1][0].lower() == "in" and toks[-1][1] == "normal":
            toks[-1] = ("in " + w, "pill"); i += 1; continue
        toks.append((w, "normal")); i += 1
    if toks and toks[-1][1] != "pill":   # 胶囊只在主句末尾成立，否则还原为普通词
        toks = [(w, "normal") if k == "pill" else (w, k) for w, k in toks]
    if not accent_word:
        for w, k in toks:
            if k == "normal" and len(re.sub(r"[^A-Za-z]", "", w)) >= 8:
                accent_word = w; break
    if not accent_word:   # 兜底：取最长的 ≥5 字母实词，保证花字总是出现
        cand = [(len(re.sub(r"[^A-Za-z]", "", w)), w) for w, k in toks if k == "normal"]
        cand = [c for c in cand if c[0] >= 5]
        if cand: accent_word = max(cand)[1]
    return [(w, "accent" if (k == "normal" and w == accent_word) else k) for w, k in toks]

def _tok_lines(d, toks, f_sans, f_serif, f_pill, pad, max_w):
    lines, cur, curw = [], [], 0
    sp = d.textlength(" ", font=f_sans)
    for w, k in toks:
        tw = d.textlength(re.sub(r"[^\w\s]", "", w), font=f_pill) + 2*pad if k == "pill" else d.textlength(w, font=(f_serif if k == "accent" else f_sans))
        add = tw if not cur else tw + sp
        if curw + add <= max_w or not cur: cur.append((w, k, tw)); curw += add
        else: lines.append(cur); cur = [(w, k, tw)]; curw = tw
    if cur: lines.append(cur)
    return lines, sp

def make_cover(base_path, title, subtitle, out_path, badge=None, style="left",
               width_ratio=0.46, theme="auto", accent=None, accent_word=None, tags=None):
    if style in ("center",): style = "left"          # 旧 align="center" 兼容 → 左对齐版式
    try: style = float(style)                        # 旧数值偏移兼容
    except (ValueError, TypeError): pass
    img = Image.open(base_path).convert("RGB"); W, H = img.size
    if style == "poster":                            # 底部渐变遮罩
        ov = Image.new("L", (1, H), 0)
        for yy in range(H):
            t = max(0, (yy - 0.42*H) / (0.58*H)); ov.putpixel((0, yy), int(215 * t**1.4))
        ov = ov.resize((W, H))
        img = Image.composite(Image.new("RGB", (W, H), (8, 10, 14)), img, ov)
    if style == "poster-white":                      # 顶部白色渐变遮罩(浅色花哨底图配黑字)
        ov = Image.new("L", (1, H), 0)
        for yy in range(H):
            t = 1.0 if yy < 0.45*H else max(0.0, (0.88*H - yy) / (0.43*H))
            ov.putpixel((0, yy), int(215 * t**1.2))
        ov = ov.resize((W, H))
        img = Image.composite(Image.new("RGB", (W, H), (250, 250, 252)), img, ov)
    d = ImageDraw.Draw(img)

    left = img.crop((0, 0, int(0.5*W), H)).resize((64, 64))
    lum = sum(0.299*r+0.587*g+0.114*b for r, g, b in left.getdata()) / 4096
    dark_bg = lum < 128
    if theme == "white": dark_bg = True
    if theme == "black": dark_bg = False
    if style == "poster": dark_bg = True   # 遮罩版式永远白字
    if style == "poster-white": dark_bg = False      # 白遮罩版式永远黑字
    TITLE_C = (245, 245, 247) if dark_bg else (17, 17, 17)
    SUB_C = (255, 255, 255) if theme == "white" else ((196, 196, 204) if dark_bg else (70, 70, 74))
    BADGE_BG = (245, 245, 247) if dark_bg else (17, 17, 17)
    BADGE_TX = (17, 17, 17) if dark_bg else (255, 255, 255)
    AC = _hex(accent) if accent else None
    fancy = bool(AC) and not is_cjk(title)
    if AC:
        AC = _boost(AC, 1.45, 1.0)                    # 花字整体提饱和
        # 对比度保险：与文字区实际背景亮度差不足则向白/黑偏移，直到醒目
        def _lum(c): return 0.299*c[0] + 0.587*c[1] + 0.114*c[2]
        bg_lum = lum
        target = (255, 255, 255) if dark_bg or bg_lum > 128 and _lum(AC) < bg_lum else ((255,255,255) if dark_bg else (0,0,0))
        toward = (255, 255, 255) if dark_bg else ((0, 0, 0) if _lum(AC) < bg_lum else (255, 255, 255))
        guard = 0
        while abs(_lum(AC) - bg_lum) < 85 and guard < 8:
            AC = _boost(_mix(AC, toward, 0.22), 1.15, 1.0); guard += 1
        PILL_BG = _boost(AC, 1.2, 0.75) if dark_bg else _boost(_mix(AC, (255, 255, 255), 0.25), 1.3, 1.0)
        PILL_TX = (250, 250, 250) if dark_bg else (25, 25, 30)
        SEC_C = _mix(AC, (255, 255, 255), 0.5 if style == "poster" else 0.25) if dark_bg else _mix(AC, (0, 0, 0), 0.2)
    else:
        SEC_C = SUB_C

    centered = style == "center"
    mx = int((0.05 if style == "poster" else 0.068) * W)
    max_w = int(width_ratio * W)
    t0 = {"poster": 0.120, "center": 0.100, "bottom": 0.095}.get(style, 0.098)
    t_size = int(t0 * H); s_size = int(0.040 * H)
    cjk = is_cjk(title)
    badge_h = int(0.052*H) + int(0.045*H) if badge else 0
    MAX_BLOCK = int((0.62 if style in ("bottom", "poster") else 0.80) * H)

    primary, secondary = _split_title(title) if fancy else (title, [])
    toks = _tokens(primary, accent_word) if fancy else None

    while True:
        tf = ImageFont.truetype(F(BOLD_CJK if cjk else BOLD_LAT), t_size)
        sf = ImageFont.truetype(F(REG_CJK if cjk else REG_LAT), s_size)
        line_h = int(t_size * 1.06)
        sec_f = ImageFont.truetype(F(BOLD_LAT), int(t_size * 0.5))
        if fancy:
            serif_f = ImageFont.truetype(F(SERIF_IT), int(t_size * 1.05))
            pill_f = ImageFont.truetype(F(BOLD_LAT), int(t_size * 0.5))
            pill_pad = int(t_size * 0.28)
            tlines, sp = _tok_lines(d, toks, tf, serif_f, pill_f, pill_pad, max_w)
        else:
            tlines = wrap(d, primary, tf, max_w); sp = 0
        sec_lines = []
        for stext in secondary: sec_lines += wrap(d, stext, sec_f, max_w)
        sec_h = len(sec_lines) * int(t_size * 0.72)
        s_lines = wrap(d, subtitle, sf, max_w) if subtitle else []
        s_line_h = int(s_size * 1.55)
        tag_h = int(0.10 * H) if tags else 0
        gap = int(0.05 * H)
        block_h = badge_h + len(tlines)*line_h + sec_h + (gap + len(s_lines)*s_line_h if s_lines else 0) + tag_h
        if block_h <= MAX_BLOCK or t_size <= int(0.045 * H): break
        t_size = int(t_size * 0.93); s_size = max(int(s_size * 0.97), int(0.028 * H))

    if style in ("top", "poster-white"): y = int(0.085 * H)
    elif style in ("bottom", "poster"): y = int(0.94 * H) - block_h
    elif isinstance(style, float): y = int(style * H)
    else: y = (H - block_h) // 2

    def linew(ln):
        if fancy: return sum(t[2] for t in ln) + sp * (len(ln) - 1)
        return d.textlength(ln, font=tf)

    if badge:
        bf = ImageFont.truetype(F(BOLD_CJK if is_cjk(badge) else BOLD_LAT), int(0.035 * H))
        bw = d.textlength(badge, font=bf); pad = int(0.012 * W)
        bx = (W - bw - 2*pad) // 2 if centered else mx
        d.rounded_rectangle([bx, y, bx + bw + 2*pad, y + int(0.052*H)], radius=int(0.026*H), fill=BADGE_BG)
        d.text((bx + pad, y + int(0.007*H)), badge, font=bf, fill=BADGE_TX)
        y += badge_h

    for ln in tlines:
        x = ((W - linew(ln)) // 2) if centered else mx
        if fancy:
            for w, k, tw in ln:
                if k == "pill":
                    ph = int(t_size * 0.72); py = y + int(t_size * 0.28)
                    d.rounded_rectangle([x, py, x + tw, py + ph], radius=ph//2, fill=PILL_BG)
                    d.text((x + pill_pad, py + int(ph*0.16)), re.sub(r"[^\w\s]", "", w), font=pill_f, fill=PILL_TX)
                elif k == "accent":
                    d.text((x, y - int(t_size*0.04)), w, font=serif_f, fill=AC)
                else:
                    d.text((x, y), w, font=tf, fill=TITLE_C)
                x += tw + sp
        else:
            d.text((x, y), ln, font=tf, fill=TITLE_C)
        y += line_h
    for ln in sec_lines:
        x = ((W - d.textlength(ln, font=sec_f)) // 2) if centered else mx
        d.text((x, y + int(t_size*0.08)), ln, font=sec_f, fill=SEC_C)
        y += int(t_size * 0.72)
    if s_lines:
        y += gap
        for ln in s_lines:
            x = ((W - d.textlength(ln, font=sf)) // 2) if centered else mx
            d.text((x, y), ln, font=sf, fill=SUB_C)
            y += s_line_h
    if tags:
        y += int(0.015 * H)
        pf = ImageFont.truetype(F(BOLD_LAT), int(0.034 * H))
        hgt = int(0.072 * H)
        widths = [d.textlength(t, font=pf) + 2*int(0.016*W) for t in tags]
        total = sum(widths) + int(0.015*W) * (len(tags) - 1)
        x = ((W - total) // 2) if centered else mx
        for t, tw in zip(tags, widths):
            fill = (255, 255, 255, 235) if not dark_bg else (255, 255, 255, 40)
            outline = _mix(AC, (0,0,0), 0.1) if AC else ((130,120,220) if not dark_bg else (220,220,230))
            d.rounded_rectangle([x, y, x + tw, y + hgt], radius=hgt//2,
                                fill=(255,255,255) if not dark_bg else None, outline=outline, width=max(2, W//700))
            d.text((x + int(0.016*W), y + int(hgt*0.2)), t, font=pf,
                   fill=(40, 40, 60) if not dark_bg else (240, 240, 245))
            x += tw + int(0.015*W)

    img.save(out_path)
    print("saved:", out_path, img.size)

if __name__ == "__main__":
    a = sys.argv
    make_cover(a[1], a[2], a[3], a[4],
               a[5] if len(a) > 5 else None,
               a[6] if len(a) > 6 else "left",
               float(a[7]) if len(a) > 7 else 0.46,
               a[8] if len(a) > 8 else "auto",
               a[9] if len(a) > 9 and a[9] != "none" else None,
               a[10] if len(a) > 10 and a[10] != "none" else None,
               a[11].split(",") if len(a) > 11 else None)
