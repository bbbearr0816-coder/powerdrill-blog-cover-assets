# -*- coding: utf-8 -*-
"""底图自动分析器：侦测主视觉位置/干净区/明暗/主色 → 输出版式决策"""
import cv2, numpy as np

def analyze(path):
    im = cv2.imread(path); H, W = im.shape[:2]
    s = cv2.resize(im, (344, 194)); h, w = s.shape[:2]
    gray = cv2.cvtColor(s, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(s, cv2.COLOR_BGR2HSV)
    # 背景色估计：四边框像素中位数
    border = np.concatenate([s[0:8].reshape(-1,3), s[-8:].reshape(-1,3), s[:,0:8].reshape(-1,3), s[:,-8:].reshape(-1,3)])
    bg = np.median(border, axis=0)
    # 忙碌度 = 梯度 + 与背景色的差异 + 饱和度
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0); gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
    grad = np.sqrt(gx**2 + gy**2); grad /= (grad.max() + 1e-6)
    dist = np.linalg.norm(s.astype(np.float32) - bg, axis=2); dist /= (dist.max() + 1e-6)
    sat = hsv[..., 1].astype(np.float32) / 255
    lvar = cv2.GaussianBlur(cv2.Laplacian(gray, cv2.CV_32F)**2, (0,0), 3); lvar/= (lvar.max()+1e-6)
    busy = cv2.GaussianBlur(0.5*grad + 0.3*lvar + 0.15*dist + 0.05*sat, (0, 0), 5)
    bmask = busy > max(0.22, busy.mean() + 0.5*busy.std())
    ys, xs = np.nonzero(bmask)
    cx, cy = (xs.mean()/w, ys.mean()/h) if len(xs) else (0.5, 0.5)
    x5 = np.percentile(xs, 5)/w if len(xs) else 0.6   # 主体左缘
    def clean(x1, y1, x2, y2):
        r = bmask[int(y1*h):int(y2*h), int(x1*w):int(x2*w)]
        return 1 - r.mean() if r.size else 1
    zones = {"left": clean(0.04, 0.08, 0.50, 0.92), "top": clean(0.04, 0.06, 0.96, 0.42),
             "bottom": clean(0.04, 0.60, 0.96, 0.96), "center": clean(0.25, 0.15, 0.75, 0.75)}
    # 明暗：干净区平均亮度
    lum_map = cv2.cvtColor(s, cv2.COLOR_BGR2GRAY)
    clean_lum = lum_map[~bmask].mean() if (~bmask).sum() else lum_map.mean()
    # 主色：忙碌且高饱和像素的 KMeans 主簇
    pix = s[bmask & (hsv[...,1] > 60)].reshape(-1, 3).astype(np.float32)
    accent = None
    if len(pix) > 200:
        _, lab, cen = cv2.kmeans(pix, 3, None, (cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0), 3, cv2.KMEANS_PP_CENTERS)
        counts = np.bincount(lab.flatten(), minlength=3)
        c = cen[counts.argmax()][::-1]  # BGR->RGB
        # 深底提亮 / 浅底压暗，保证强调色可读
        t = 0.45 if clean_lum < 128 else 0.0
        c = c*(1-t) + np.array([255,255,255])*t
        if clean_lum >= 128: c = c*0.75
        accent = "#%02x%02x%02x" % tuple(int(v) for v in c)
    # 版式决策
    lb = bmask[:, :w//2].mean(); rb = bmask[:, w//2:].mean()
    if rb > 2.2*lb and lb < 0.30:               # 明显左右构图 → 左对齐
        style, align, width = "left", "left", round(min(0.62, max(0.38, x5 - 0.09)), 2)
    elif cy > 0.68 and zones["top"] > 0.85:      # 主体在下 → 顶部宽排优先
        style, align, width = "top", "top", 0.62
    elif zones["left"] > 0.80:
        style, align, width = "left", "left", round(min(0.62, max(0.38, x5 - 0.09)), 2)
    elif zones["top"] > 0.80:
        style, align, width = "top", "top", 0.62
    elif zones["bottom"] > 0.78:
        style, align, width = "bottom", "bottom", 0.62
    elif zones["center"] > 0.85:
        style, align, width = "center", "center", 0.70
    else:
        style, align, width = "poster", "poster", 0.80
    theme = "white" if clean_lum < 135 else "black"
    return {"style": style, "align": align, "width": width, "theme": theme, "accent": accent,
            "subject": (round(cx,2), round(cy,2)), "zones": {k: round(v,2) for k,v in zones.items()}}

if __name__ == "__main__":
    import glob, os, json
    base = "/sessions/beautiful-trusting-heisenberg/mnt/Blog底图/底图"
    for f in sorted(glob.glob(base + "/*/*.png")):
        if "_备用" in f: continue
        r = analyze(f)
        rel = os.path.relpath(f, base)
        print(f"{rel:38s} {r['style']:8s} 主体({r['subject'][0]},{r['subject'][1]}) 宽{r['width']} {r['theme']:5s} {r['accent']} 区:{r['zones']}")
