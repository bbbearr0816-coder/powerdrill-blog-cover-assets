---
name: blog-cover
description: Generate a Powerdrill blog cover image (博客封面) from an article URL or a title + category. Use this skill whenever the user asks for a blog cover, 封面, cover image, header image, or OG image for a Powerdrill blog post — including requests like "给这篇文章出封面", "make a cover for this post", or when they paste a powerdrill.ai/blog/... link and ask for any kind of image for it. Also use it for batch requests like "generate covers for this week's articles".
---

# Powerdrill Blog Cover Generator

Compose a finished blog cover: a category-specific background (底图, pulled from a central GitHub asset repo) + auto-typeset title, subtitle and category badge. Typography is rendered programmatically, so every cover is consistent and no design tool is needed.

## Inputs

- **An article URL** (`https://powerdrill.ai/blog/<slug>` or `/zh-CN/blog/<slug>`) — preferred.
- **A title + category** (optional subtitle) when the article isn't published yet.

## Always output English covers

No matter what language the input is:
- Given a `/zh-CN/blog/<slug>` URL, fetch the English original at `https://powerdrill.ai/blog/<slug>` and use its English `og:title` / `meta-description`.
- Given a Chinese title with no URL, locate the English original on powerdrill.ai first. Never machine-translate when an official English title exists; only translate as a last resort and say so.

## Workflow

### 1. Get article metadata

Fetch the URL and extract: **Title** (`og:title`/`<h1>`), **Subtitle** (`meta-description`; truncate at first sentence if >~140 chars), **Category** (breadcrumb link, e.g. `/blog/data-insights` → Data Insights).

### 2. Pick the background (底图)

Assets live in the company Cloudflare R2 bucket (`agent-loops-powerdrill/blog-cover-assets/`, primary; requires `~/.config/powerdrill-r2.env` with R2 credentials) with a GitHub repo fallback (`bbbearr0816-coder/powerdrill-blog-cover-assets`). The bundled `scripts/assets.py` picks the source automatically (`assets.py source` shows which) and caches locally — users need no local folder:

```bash
python3 <skill-path>/scripts/assets.py layout                 # layout.json（每张底图的排版参数）
python3 <skill-path>/scripts/assets.py list tips              # 列出类目下的底图变体
python3 <skill-path>/scripts/assets.py fetch tips/default.png # 下载底图，打印本地路径
```

If the user connected a local asset folder (contains category subfolders + layout.json), prefer it: set `LOCAL_ASSETS=<该目录>` in the environment when calling assets.py — designers use this to test unpublished assets.

Category → folder → badge text: Tips→`tips/`→TIPS; Use Case→`use-case/`→USE CASE; Polymarket→`polymarket/`→POLYMARKET; Data Insights→`data-insights/`→DATA INSIGHTS; Glossary→`glossary/`→GLOSSARY; News→`news/`→NEWS; Research Digest→`research-digest/`→RESEARCH DIGEST. Folders starting with `_` are spares — never select from them.

**Variant selection** — same category must not always ship the same artwork:
1. **Keyword match first.** Filenames are keyword tokens (`excel.png`, `funnel.png`, `crypto.png`). If a token or close synonym appears in the title, prefer that variant — match semantically ("spreadsheets"→excel, GPT/Claude→ai-model, Bitcoin→crypto).
2. **Otherwise rotate deterministically:** hash the slug modulo variant count — variety spreads evenly, re-runs stable.

If a category has no assets, list what exists and ask — don't substitute another category.

### 3. Layout parameters

Priority, highest first:
1. **layout.json entry** for the chosen background's relative path — designer-tuned. Fields: `align`(版式)/`width`/`theme`/`accent`/`no_sub`。`accent: "none"` = 关闭花字（彩色花哨底图一律 none；深色简洁底图才用花字）。`no_sub: true` = 不渲染副标题（文字安全区较矮的底图）。
2. **Auto analysis** for unlisted assets: `python3 <skill-path>/scripts/auto_layout.py` 侦测主体位置/干净区/明暗/主色并推荐参数（其 style 输出直接对应渲染器）。
3. Defaults: `left` / 0.46 / `auto`。

### 4. Compose

```bash
python3 <skill-path>/scripts/make_cover.py <底图路径> "<title>" "<subtitle>" <输出.png> "<badge>" [style] [width] [theme] [accent] [accent_word] [tags]
```

- **style**: `left`(默认) / `top` / `bottom` / `center` / `poster`(自动加底部深色渐变遮罩、永远白字、对底图要求最低)/ `poster-white`(顶部白色渐变遮罩、永远黑字,适合浅色但主体杂乱的底图)；数值如 `0.17` 表示距顶比例。
- **width**: 标题区宽度比例。越大越晚换行；主体压左侧时调小（0.36–0.44），底部铺满型配 `top`+0.60–0.66。
- **theme**: `auto`/`white`/`black`。中等亮度彩色底图自动判色不可靠，layout.json 已固化。
- **accent**: 强调色 hex 或 `"none"`。启用时：标题第一个长实词衬线斜体花字、行尾 "in 20XX" 年份胶囊、问号/冒号后次要句降级小字。花字自动提饱和且带对比度保险（与背景亮度差 <85 自动调整）。
- **tags**: 逗号分隔关键词胶囊行（可选，取文章 tags 前 3 个短词）。

排版引擎自动处理：中英文换行（中文含标点禁则）、1.06 紧凑行距、自动缩字（超 80% 安全高度）、深浅底自动黑白字。

Requirements: Python 3 + Pillow + curl. 字体无需预装：渲染器按平台自动查找（Linux Noto/Liberation、macOS Arial/Times、Windows 雅黑/Arial），找不到时自动从 notofonts 官方仓库下载 Noto 字体到 `/tmp/pd-cover-assets/fonts/` 缓存（英文封面约 2MB，含中文标题时约 16MB，仅首次）。也可用环境变量 `PD_FONT_BOLD_LAT` 等按角色指定字体路径。若 Pillow 缺失：`python3 -m pip install --user Pillow`。

### 5. Deliver

- Output `cover_<slug>.png`, save to the user's connected folder (or outputs if none), present the file.
- Batch requests: process each article, present all at the end.

## Quality checks

- Title must match the article title exactly — never paraphrase.
- Render and eyeball: text must not sit on prominent artwork; retry with smaller width or `top` if it does, and report the asset.
- Very long titles auto-shrink — confirm thumbnail legibility.

## Asset repo maintenance (for designers)

新底图入库：上传 PNG 到 R2 桶 `blog-cover-assets/` 对应类目前缀下（16:9、≥1920 宽、无文字、主体靠右/左侧留白），文件名用英文关键词；需要专属排版参数时在 layout.json 加一条(同前缀下)。GitHub 仓库为兜底源,重要更新建议双写保持同步。替换已有图片必须换新文件名(各机器图片缓存按文件名,同名覆盖不刷新)。
