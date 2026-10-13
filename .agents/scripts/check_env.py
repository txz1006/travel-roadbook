#!/usr/bin/env python3
"""环境预检 —— 本机缺什么、因此哪几项检查将不执行。

为什么需要它：三个校验脚本各有依赖，缺依赖时的默认表现是「报错退出」或「静默跳过」。
前者让人以为页面有问题，后者更糟——会让人以为检查通过了。本脚本把结论说在前面：
哪些能跑，哪些跑不了，跑不了的后果是什么。

用法：
    python .agents/scripts/check_env.py            # 只报告，始终退出 0
    python .agents/scripts/check_env.py --strict   # 有任何缺失就退出 1（给 CI 用）

依赖：仅标准库。
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(AGENT_ROOT)
BASELINE_DIR = os.path.join(AGENT_ROOT, "assets", "fonts-baseline")

OK = "✓"
NO = "✗"
NOTE = "·"

PY_DEPS = [
    # 模块名, 中文名, 缺失时哪项检查不执行
    ("fontTools", "fontTools", "字体子集切分（subset_fonts.py）"),
    ("PIL", "Pillow", "二维码核验（decode_qr.py）"),
    ("zxingcpp", "zxing-cpp", "二维码核验（decode_qr.py）"),
]
PY_OPTIONAL = [
    ("py7zr", "py7zr", "仅在重建基线且需从上游 7z 包下载全量字体时用到"),
]

# 模块名 → pip 包名（取版本号用）
PIP_NAMES = {"fontTools": "fonttools", "PIL": "Pillow", "zxingcpp": "zxing-cpp", "py7zr": "py7zr"}


def module_version(mod):
    try:
        from importlib.metadata import version  # noqa: PLC0415

        return version(PIP_NAMES.get(mod, mod))
    except Exception:  # noqa: BLE001
        pass
    try:
        m = __import__(mod)
        return getattr(m, "__version__", "") or getattr(m, "VERSION", "") or ""
    except Exception:  # noqa: BLE001
        return ""

# Playwright 浏览器的候选根目录与可执行文件相对路径（与 verify_page.js 保持一致）
PW_ROOTS = [
    os.environ.get("PLAYWRIGHT_BROWSERS_PATH"),
    os.path.join(os.path.expanduser("~"), "AppData", "Local", "ms-playwright"),
    os.path.join(os.path.expanduser("~"), "Library", "Caches", "ms-playwright"),
    os.path.join(os.path.expanduser("~"), ".cache", "ms-playwright"),
    "/ms-playwright",
]
PW_BINS = [
    ("chrome-win64", "chrome.exe"),
    ("chrome-win", "chrome.exe"),
    ("chrome-mac", "Chromium.app", "Contents", "MacOS", "Chromium"),
    ("chrome-mac-arm64", "Chromium.app", "Contents", "MacOS", "Chromium"),
    ("chrome-linux", "chrome"),
    ("chrome-headless-shell-win64", "chrome-headless-shell.exe"),
    ("chrome-headless-shell-mac-arm64", "chrome-headless-shell"),
    ("chrome-headless-shell-linux64", "chrome-headless-shell"),
]


def human(nbytes):
    return f"{nbytes / 1024 / 1024:.1f} MB" if nbytes >= 1024 * 1024 else f"{nbytes / 1024:.0f} KB"


def sha256_prefix(path, n=12):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:n]


def check_python():
    print(f"Python  {sys.executable}")
    print(f"        版本 {sys.version.split()[0]}")
    missing = []
    for mod, label, consequence in PY_DEPS:
        try:
            spec = importlib.util.find_spec(mod)
        except (ImportError, ValueError):
            spec = None
        if spec is None:
            missing.append(consequence)
            print(f"  {NO} {label:<14} 未安装     → 将不执行：{consequence}")
        else:
            print(f"  {OK} {label:<14} {module_version(mod):<10}")
    for mod, label, note in PY_OPTIONAL:
        if importlib.util.find_spec(mod):
            print(f"  {OK} {label:<14} {module_version(mod):<10}")
        else:
            print(f"  {NOTE} {label:<14} 未安装     → {note}")
    print()
    return missing


def check_node():
    print("Node")
    node = shutil.which("node")
    if not node:
        print(f"  {NO} node          未找到     → 将不执行：页面回归校验（verify_page.js）")
        print()
        return ["页面回归校验（verify_page.js）"]

    try:
        version = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:  # noqa: BLE001
        version = "?"
    print(f"  {OK} node          {version}")

    probe = "try{console.log(require.resolve('playwright-core'))}catch(e){process.exit(3)}"
    pw_ok = False
    try:
        r = subprocess.run([node, "-e", probe], capture_output=True, text=True, timeout=40, cwd=REPO_ROOT)
        if r.returncode == 0:
            pw_ok = True
            print(f"  {OK} playwright-core {r.stdout.strip()}")
        else:
            print(f"  {NO} playwright-core 未解析到   → 在仓库根跑 npm install")
    except Exception:  # noqa: BLE001
        print(f"  {NO} playwright-core 探测失败")

    chrome = find_chromium()
    if chrome:
        print(f"  {OK} Chromium      {chrome}")
    else:
        print(f"  {NO} Chromium      未找到     → 先跑 npx playwright install chromium")
        print(f"                      或用 ROADBOOK_CHROME=<可执行文件路径> 指定")

    print()
    # playwright-core 与 Chromium 缺任何一个，页面回归都跑不了
    if pw_ok and chrome:
        return []
    return ["页面回归校验（verify_page.js）"]


def find_chromium():
    override = os.environ.get("ROADBOOK_CHROME") or os.environ.get("CHROMIUM_EXECUTABLE_PATH")
    if override:
        return override if os.path.exists(override) else None

    for root in [r for r in PW_ROOTS if r and os.path.isdir(r)]:
        try:
            dirs = os.listdir(root)
        except OSError:
            continue
        dirs = [d for d in dirs if re.match(r"^(chromium_headless_shell|chromium)-\d+$", d)]
        dirs.sort(key=lambda d: (0 if d.startswith("chromium-") else 1, -int(d.split("-")[1])))
        for d in dirs:
            for parts in PW_BINS:
                p = os.path.join(root, d, *parts)
                if os.path.exists(p):
                    return p
    return None


def check_baseline():
    print("字体基线  .agents/assets/fonts-baseline/")
    if not os.path.isdir(BASELINE_DIR):
        print(f"  {NO} 目录不存在 → 将不执行：字体子集切分")
        print()
        return ["字体子集切分（subset_fonts.py）"]

    missing = []
    for name in ("wenkai-broad.woff2", "sarasa-broad.woff2", "font-charset-broad.txt", "baseline.json"):
        p = os.path.join(BASELINE_DIR, name)
        if not os.path.exists(p):
            missing.append(name)
            print(f"  {NO} {name:<24} 缺失")
            continue
        extra = f"{human(os.path.getsize(p))}"
        if name.endswith(".woff2"):
            extra += f"  sha256:{sha256_prefix(p)}"
        elif name == "font-charset-broad.txt":
            with open(p, encoding="utf-8") as f:
                content = f.read()
            # 注意：字符集里含空格字符，不能用 strip()，否则会少算一个
            extra += f"  {len(content.rstrip(chr(10) + chr(13))):,} 字"
        print(f"  {OK} {name:<24} {extra}")

    # 等价性证明是否完好（基线可信度的关键证据）
    # 注意：equivalence_proof 是「字典」——method / <字体 slug> / verified_at，不是数组
    meta_path = os.path.join(BASELINE_DIR, "baseline.json")
    if os.path.exists(meta_path):
        try:
            meta = json.load(open(meta_path, encoding="utf-8"))
            proof = meta.get("equivalence_proof") or {}
            entries = [v for v in proof.values() if isinstance(v, dict) and "equivalent" in v]
            good = sum(1 for x in entries if x.get("equivalent") is True)
            if entries and good == len(entries):
                print(f"  {OK} 等价性证明    {good}/{len(entries)} 项 equivalent=true（基线切出的子集 ≡ 全量直切）")
            elif entries:
                print(f"  {NOTE} 等价性证明    {good}/{len(entries)} 项 equivalent=true —— 有项不成立，基线不可信")
            else:
                print(f"  {NOTE} 等价性证明    baseline.json 里没有可读的证明条目")
        except Exception as e:  # noqa: BLE001
            print(f"  {NOTE} baseline.json 解析失败：{e}")

    for lic in ("OFL-LXGWWenKaiScreen.txt", "OFL-SarasaGothic.txt"):
        p = os.path.join(BASELINE_DIR, lic)
        print(f"  {OK if os.path.exists(p) else NO} {lic:<24} {'许可文件在' if os.path.exists(p) else '缺失（再分发前必须补回）'}")

    print()
    return ["字体子集切分（subset_fonts.py）"] if missing else []


def main():
    ap = argparse.ArgumentParser(description="travel-roadbook 环境预检")
    ap.add_argument("--strict", action="store_true", help="有任何缺失时退出码 1（给 CI 用）")
    args = ap.parse_args()

    print()
    print("travel-roadbook 环境预检")
    print("=" * 60)
    print()

    blocked = []
    blocked += check_python()
    blocked += check_node()
    blocked += check_baseline()

    scripts = [
        ("subset_fonts.py", "字体子集切分", "字体子集切分（subset_fonts.py）"),
        ("verify_page.js", "页面回归校验", "页面回归校验（verify_page.js）"),
        ("decode_qr.py", "二维码核验", "二维码核验（decode_qr.py）"),
        ("make_font_baseline.py", "重建字体基线", "重建字体基线（make_font_baseline.py）"),
    ]
    blocked_set = set(blocked)
    print("可执行的检查")
    for _, label, key in scripts:
        if key in blocked_set:
            print(f"  {NO} {label}")
        else:
            print(f"  {OK} {label}")
    print()

    if not blocked:
        print("结论：全部可用。交付前按 AGENTS.md 第 5 节跑一遍即可。")
    else:
        print("结论：以下检查在本机不执行，交付时必须如实写明——")
        for b in blocked:
            print(f"  {NO} {b}")
        print()
        print("装齐的方式：")
        print("  pip install -r requirements.txt")
        print("  npm install && npx playwright install chromium")
        print("不装也能用，但交付里不得声称这些检查已通过。")
    print()

    return 1 if (args.strict and blocked) else 0


if __name__ == "__main__":
    sys.exit(main())
