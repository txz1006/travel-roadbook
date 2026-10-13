#!/usr/bin/env python3
"""字体子集化。

把计划页用到的字符切成两个极小的 woff2，供 index.html 离线自包含引用。

核心设计：**自带基线 + 覆盖校验 + 自动回退**
  基线（assets/fonts-baseline/*.woff2，6.7 MB）替代全量源字体（48.9 MB），
  从基线切出的结果与从全量直切逐字节一致（见 baseline.json 的 equivalence_proof）。
  切完会逐字核对输出 cmap；若基线没覆盖某个字符，自动回退全量字体重切，绝不静默丢字。

用法：
    python subset_fonts.py <plan-dir>                 # 常规：基线快路径
    python subset_fonts.py <plan-dir> --strict        # 优先用全量 TTF（更慢，结果同）
    python subset_fonts.py <plan-dir> --shared DIR    # 指定 _shared/fonts 位置

产物：<plan-dir>/assets/fonts/{lxgw-wenkai-screen-subset,sarasa-mono-sc-subset}.woff2
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT_ROOT = os.path.dirname(HERE)
BASELINE_DIR = os.path.join(AGENT_ROOT, "assets", "fonts-baseline")
BASELINE_META = os.path.join(BASELINE_DIR, "baseline.json")

# 全量源字体的一次性缓存（只在基线覆盖不到时才用）
# 与客户端无关的默认位置，可用 TRAVEL_ROADBOOK_FONT_CACHE 覆盖
USER_CACHE = os.environ.get("TRAVEL_ROADBOOK_FONT_CACHE") or os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache"),
    "travel-roadbook", "fonts",
)

# 字体定义。slug 同时用作 baseline.json 的键，保持稳定，勿随意改。
FONTS = [
    {
        "key": "wenkai",
        "slug": "lxgw-wenkai-screen",
        "family": "LXGW WenKai Screen",
        "out": "lxgw-wenkai-screen-subset",
        "baseline": "wenkai-broad.woff2",
        "full": "wenkai.ttf",
        "url": "https://github.com/lxgw/LxgwWenKai-Screen/releases/download/v1.520/LXGWWenKaiScreen.ttf",
        "archive_member": None,
        "source": {
            "repo": "lxgw/LxgwWenKai-Screen",
            "tag": "v1.520",
            "asset": "LXGWWenKaiScreen.ttf",
            "license": "OFL-1.1",
            "license_file": "OFL-LXGWWenKaiScreen.txt",
        },
    },
    {
        "key": "sarasa",
        "slug": "sarasa-mono-sc",
        "family": "Sarasa Mono SC",
        "out": "sarasa-mono-sc-subset",
        "baseline": "sarasa-broad.woff2",
        "full": "SarasaMonoSC-Regular.ttf",
        "url": "https://github.com/be5invis/Sarasa-Gothic/releases/download/v1.0.42/SarasaMonoSC-TTF-1.0.42.7z",
        "archive_member": "SarasaMonoSC-Regular.ttf",
        "source": {
            "repo": "be5invis/Sarasa-Gothic",
            "tag": "v1.0.42",
            "asset": "SarasaMonoSC-TTF-1.0.42.7z",
            "license": "OFL-1.1",
            "license_file": "OFL-SarasaGothic.txt",
            "extract_note": "需 py7zr 解包（环境内无 7z 可执行文件）",
        },
    },
]

SUBSET_OPTS = [
    "--layout-features=*", "--no-hinting", "--desubroutinize",
    "--drop-tables+=DSIG", "--name-IDs=*", "--recalc-bounds", "--flavor=woff2",
]


# ---------------------------------------------------------------- 字符收集

def collect_chars(html_path):
    """收集页面要用到的全部字符（正文字体）与等宽字体字符。"""
    html = open(html_path, encoding="utf-8").read()

    all_chars = set(html)
    all_chars |= set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    all_chars |= set(" .,:;!?()[]{}<>/\\|@#$%^&*-_=+\"'`~")
    for c in "\n\r\t":
        all_chars.discard(c)

    mono = set(
        "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        " .,:;?!()[]/\\|%+-–—×·¥$&'\"`~<>=_@#"
    )
    # 等宽字体常被用在含中文的元素上（.num / .mono 里夹单位），补一批高频字
    mono |= set("元公里米人天晚间时约无未含包车门海拔步行住餐")
    for m in re.finditer(r"<code>(.*?)</code>", html, re.S):
        mono |= set(re.sub(r"<[^>]+>", "", m.group(1)))
    for m in re.finditer(r'<(\w+)[^>]*class="[^"]*\b(?:num|mono)\b[^"]*"[^>]*>(.*?)</\1>', html, re.S):
        mono |= set(re.sub(r"<[^>]+>", "", m.group(2)))
    mono.discard("\n")
    return all_chars, mono


# ---------------------------------------------------------------- 基线定位

def load_meta():
    if os.path.isfile(BASELINE_META):
        return json.load(open(BASELINE_META, encoding="utf-8"))
    return {}


def autodetect_shared(plan_dir):
    """从计划目录向上找 _shared/fonts（最多 3 层）。"""
    cur = os.path.abspath(plan_dir)
    for _ in range(4):
        cand = os.path.join(cur, "_shared", "fonts")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


def pick_base(font, args, shared_dir):
    """返回 (路径, 说明)。按速度与可得性排序。"""
    full_candidates = []
    if shared_dir:
        full_candidates.append(("工作区 _shared/fonts", os.path.join(shared_dir, font["full"])))
    full_candidates.append(("用户级缓存", os.path.join(USER_CACHE, font["full"])))

    if args.strict:
        for label, p in full_candidates:
            if os.path.isfile(p):
                return p, f"全量·{label}"
    else:
        b = os.path.join(BASELINE_DIR, font["baseline"])
        if os.path.isfile(b):
            return b, "自带基线"
        for label, p in full_candidates:
            if os.path.isfile(p):
                return p, f"全量·{label}"
    return None, None


def ensure_full(font, shared_dir):
    """回退用：拿到全量 TTF（本地找 → 下载）。返回路径或 None。"""
    local = []
    if shared_dir:
        local.append(("工作区 _shared/fonts", os.path.join(shared_dir, font["full"])))
    local.append(("用户级缓存", os.path.join(USER_CACHE, font["full"])))
    for label, p in local:
        if os.path.isfile(p):
            return p, label

    os.makedirs(USER_CACHE, exist_ok=True)
    dst = os.path.join(USER_CACHE, font["full"])
    url = font["url"]
    print(f"    下载全量字体：{url}")
    proxy = os.environ.get("TRAVEL_ROADBOOK_PROXY") or os.environ.get("HTTPS_PROXY")
    try:
        if url.endswith(".7z"):
            tmp = os.path.join(USER_CACHE, os.path.basename(url))
            _download(url, tmp, proxy)
            import py7zr
            with py7zr.SevenZipFile(tmp, "r") as z:
                z.extract(targets=[font["archive_member"]], path=USER_CACHE)
            os.remove(tmp)
        else:
            _download(url, dst, proxy)
    except Exception as e:                                    # noqa: BLE001
        print(f"    ✗ 下载失败：{e}")
        print(f"      可手动放入：{dst}")
        print(f"      下载不走通时可用代理：TRAVEL_ROADBOOK_PROXY=http://127.0.0.1:7897")
        return None, None
    if os.path.isfile(dst):
        return dst, "已下载"
    # 7z 解出来的可能带子目录
    for root, _, files in os.walk(USER_CACHE):
        if font["full"] in files:
            return os.path.join(root, font["full"]), "已下载"
    return None, None


def _download(url, dst, proxy):
    import urllib.request
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))
    op = urllib.request.build_opener(*handlers)
    with op.open(url, timeout=180) as r, open(dst, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)


# ---------------------------------------------------------------- 子集化

def run_subset(src, chars, out, text_path):
    with open(text_path, "w", encoding="utf-8") as f:
        f.write("".join(sorted(c for c in chars if c.strip() or c == " ")))
    cmd = [sys.executable, "-m", "fontTools.subset", src,
           "--text-file=" + text_path, "--output-file=" + out] + SUBSET_OPTS
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-1200:])
        print(r.stderr[-2000:])
        raise SystemExit(f"fontTools.subset 失败：{src}")


def check_coverage(out, chars):
    """返回输出字体未覆盖的字符列表。"""
    from fontTools.ttLib import TTFont
    cmap = set(TTFont(out).getBestCmap())
    return sorted(c for c in chars if c.strip() and ord(c) not in cmap)


def main():
    ap = argparse.ArgumentParser(description="旅行路书字体子集化（基线快路径 + 覆盖校验）")
    ap.add_argument("plan_dir", help="计划目录，如 旅行计划/2026-11-xishuangbanna-5d")
    ap.add_argument("--strict", action="store_true", help="优先用全量 TTF，不用基线")
    ap.add_argument("--shared", default=None, help="_shared/fonts 目录（默认自动向上查找）")
    args = ap.parse_args()

    plan = os.path.abspath(args.plan_dir)
    html = os.path.join(plan, "index.html")
    if not os.path.isfile(html):
        raise SystemExit(f"找不到 {html}")

    fonts_dir = os.path.join(plan, "assets", "fonts")
    os.makedirs(fonts_dir, exist_ok=True)

    try:
        import fontTools  # noqa: F401
    except ImportError:
        raise SystemExit(
            "当前 Python 没有 fontTools。安装依赖后再运行：\n"
            "  pip install -r requirements.txt\n"
            "  或用带 fontTools 的解释器：<python> .agents/scripts/subset_fonts.py <plan-dir>"
        )

    shared = args.shared or autodetect_shared(plan)
    meta = load_meta()
    all_chars, mono = collect_chars(html)

    print(f"计划：{os.path.basename(plan)}")
    print(f"字符：正文 {len(all_chars)} 个 / 等宽 {len(mono)} 个")
    print(f"工作区 _shared/fonts：{shared or '（无，走基线）'}")
    if meta.get("charset"):
        print(f"基线字符集：{meta['charset']['char_count']} 字（{meta['charset']['file']}）")
    print()

    escalated = []
    for font in FONTS:
        chars = all_chars if font["key"] == "wenkai" else mono
        out = os.path.join(fonts_dir, font["out"] + ".woff2")
        txt = os.path.join(fonts_dir, "." + font["out"] + ".chars.txt")

        base, kind = pick_base(font, args, shared)
        if base is None:
            base, kind = ensure_full(font, shared)
        if base is None:
            raise SystemExit(f"{font['family']}：拿不到任何可用字源")

        run_subset(base, chars, out, txt)
        missing = check_coverage(out, chars)

        if missing:
            print(f"  ! {font['family']}：基线缺 {len(missing)} 字 {''.join(missing[:24])}")
            full, fkind = ensure_full(font, shared)
            if full:
                run_subset(full, chars, out, txt)
                missing = check_coverage(out, chars)
                kind = f"全量·{fkind}（已回退）"
                escalated.append(font["family"])
            if missing:
                print(f"    ℹ 全量字体也没有这 {len(missing)} 个字符，"
                      f"浏览器会按 font-family 回退到系统字体渲染（非乱码）：")
                print(f"      {''.join(missing[:40])}")

        os.remove(txt)
        print(f"  ✓ {font['family']:<22} {kind:<18} {len(chars):>5} 字 → "
              f"{os.path.getsize(out) / 1024:>7.1f} KB")

    print()
    if escalated:
        print(f"⚠ 有字体回退到全量源：{'、'.join(escalated)}")
        print("  说明基线字符集需要扩充 —— 跑 scripts/make_font_baseline.py 重建基线。")
    else:
        print("全部走自带基线，未下载任何字体（0 字节网络流量）。")


if __name__ == "__main__":
    main()
