#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""素材源(按优先级):
1. LOCAL_ASSETS=<本地底图目录>   设计师测试未发布素材
2. 公司 Cloudflare R2 桶          机器上存在 ~/.config/powerdrill-r2.env(或同名环境变量)时自动启用
3. GitHub 素材库                  兜底
用法:
  python3 assets.py layout            → 打印 layout.json 内容
  python3 assets.py list <category>   → 列出该类目的底图文件名
  python3 assets.py fetch <rel-path>  → 下载底图到缓存并打印本地绝对路径
  python3 assets.py source            → 打印当前生效的素材源"""
import sys, os, json, subprocess, hashlib, hmac, datetime, urllib.parse, re

REPO = "bbbearr0816-coder/powerdrill-blog-cover-assets"   # GitHub 兜底源
BRANCH = "main"
RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
API = f"https://api.github.com/repos/{REPO}/contents"
CACHE = "/tmp/pd-cover-assets"
R2_ENV_FILE = os.path.expanduser("~/.config/powerdrill-r2.env")
R2_PREFIX = "blog-cover-assets"   # 素材在桶内的前缀

def local_root():
    p = os.environ.get("LOCAL_ASSETS")
    return p if p and os.path.isdir(p) else None

def _r2_cfg():
    env = dict(os.environ)
    if os.path.isfile(R2_ENV_FILE):
        for line in open(R2_ENV_FILE):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k, v)
    need = ("CLOUDFLARE_R2_S3_API", "CLOUDFLARE_R2_S3_ACCESS_KEY_ID",
            "CLOUDFLARE_R2_S3_SECRET_ACCESS_KEY", "CLOUDFLARE_R2_BUCKET_NAME_POWERDRILL")
    if all(env.get(k) for k in need):
        return {"endpoint": env[need[0]].rstrip("/"), "ak": env[need[1]],
                "sk": env[need[2]], "bucket": env[need[3]]}
    return None

def _presign(path, query=None, expires=3600):
    """SigV4 预签名 GET(纯标准库,免装 boto3)。path 如 /bucket/key,query 为额外参数 dict"""
    cfg = _r2_cfg(); host = cfg["endpoint"].split("//")[1]
    now = datetime.datetime.utcnow()
    amzdate, datestamp = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    scope = f"{datestamp}/auto/s3/aws4_request"
    q = dict(query or {})
    q.update({"X-Amz-Algorithm": "AWS4-HMAC-SHA256", "X-Amz-Credential": f"{cfg['ak']}/{scope}",
              "X-Amz-Date": amzdate, "X-Amz-Expires": str(expires), "X-Amz-SignedHeaders": "host"})
    qpath = urllib.parse.quote(path, safe="/")
    cq = "&".join(f"{urllib.parse.quote(k, '')}={urllib.parse.quote(v, '')}" for k, v in sorted(q.items()))
    creq = "\n".join(["GET", qpath, cq, f"host:{host}\n", "host", "UNSIGNED-PAYLOAD"])
    sts = "\n".join(["AWS4-HMAC-SHA256", amzdate, scope, hashlib.sha256(creq.encode()).hexdigest()])
    key = f"AWS4{cfg['sk']}".encode()
    for part in (datestamp, "auto", "s3", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    sig = hmac.new(key, sts.encode(), hashlib.sha256).hexdigest()
    return f"{cfg['endpoint']}{qpath}?{cq}&X-Amz-Signature={sig}"

def _curl(url, out=None):
    if out:
        subprocess.run(["curl", "-sL", "--fail", "-o", out, url], check=True, timeout=120)
        return out
    r = subprocess.run(["curl", "-sL", "--fail", url], capture_output=True, check=True, timeout=60)
    return r.stdout.decode()

def layout():
    lr = local_root()
    if lr: return open(os.path.join(lr, "layout.json")).read()
    os.makedirs(CACHE, exist_ok=True)
    cfg = _r2_cfg()
    if cfg:
        return _curl(_presign(f"/{cfg['bucket']}/{R2_PREFIX}/layout.json"))
    return _curl(f"{RAW}/layout.json")

def list_cat(cat):
    lr = local_root()
    if lr:
        d = os.path.join(lr, cat)
        return [f for f in os.listdir(d) if f.endswith(".png")] if os.path.isdir(d) else []
    cfg = _r2_cfg()
    if cfg:
        xml = _curl(_presign(f"/{cfg['bucket']}", {"list-type": "2", "prefix": f"{R2_PREFIX}/{cat}/"}))
        keys = re.findall(r"<Key>([^<]+)</Key>", xml)
        return [k.rsplit("/", 1)[-1] for k in keys if k.endswith(".png")]
    return [f["name"] for f in json.loads(_curl(f"{API}/{cat}?ref={BRANCH}")) if f["name"].endswith(".png")]

def fetch(rel):
    lr = local_root()
    if lr: return os.path.join(lr, rel)
    dst = os.path.join(CACHE, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst):
        cfg = _r2_cfg()
        url = _presign(f"/{cfg['bucket']}/{R2_PREFIX}/{rel}") if cfg else f"{RAW}/{rel}"
        _curl(url, dst)
    return dst

def source():
    if local_root(): return f"LOCAL_ASSETS ({local_root()})"
    if _r2_cfg(): return f"R2 ({_r2_cfg()['bucket']}/{R2_PREFIX})"
    return f"GitHub ({REPO})"

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "layout": print(layout())
    elif cmd == "list": print("\n".join(list_cat(sys.argv[2])))
    elif cmd == "fetch": print(fetch(sys.argv[2]))
    elif cmd == "source": print(source())
