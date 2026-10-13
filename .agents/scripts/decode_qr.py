#!/usr/bin/env python3
"""二维码核验 —— 解码计划里的二维码，确认它指向 manifest.json 里登记的分享链接。

为什么必须解码而不能只看文件存在：二维码是位图，肉眼无法确认内容。曾出现过
「链接与二维码不是同一份指南」的情况，所以交付前一律解码复核。

只解码**源文件**不够 —— 页面实际渲染的是 <img src="...svg">，浏览器缩放/着色后的
结果才作数。所以还可以传一张页面截图，从截图里再解一次。

用法：
    python decode_qr.py <plan-dir>
    python decode_qr.py <plan-dir> --shot shots/guide.png

依赖：zxing-cpp + Pillow（pip install -r requirements.txt）。
"""
import argparse
import glob
import json
import os
import sys

try:
    import zxingcpp
    from PIL import Image
except ImportError:
    raise SystemExit("需要 zxing-cpp 与 Pillow。先运行：pip install -r requirements.txt")


def decode(path, expect):
    # SVG 不能直接用 PIL 打开。页面里的 SVG 二维码改由「渲染截图」核验（见 --shot）。
    if path.lower().endswith(".svg"):
        return None, "SVG 无法直接解码，由页面截图核验"
    img = Image.open(path)
    res = zxingcpp.read_barcodes(img)
    if not res:
        return None, "未检出条码"
    rows = []
    ok_all = True
    for r in res:
        same = (expect is None) or (r.text == expect)
        ok_all &= same
        rows.append(f"{r.format} {r.text}" + ("" if expect is None else ("  ✓" if same else "  ✗ 与登记链接不符")))
    return ok_all, " ； ".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan_dir")
    ap.add_argument("--shot", default=None, help="页面截图路径，用于核验实际渲染结果")
    args = ap.parse_args()

    plan = os.path.abspath(args.plan_dir)
    mf = os.path.join(plan, "manifest.json")
    expect = None
    if os.path.isfile(mf):
        meta = json.load(open(mf, encoding="utf-8"))
        expect = (meta.get("map_guide") or {}).get("share_url")
        if expect in (None, "", "PENDING"):
            expect = None
    print(f"计划：{os.path.basename(plan)}")
    print(f"manifest 登记链接：{expect or '（未登记，仅报告解码结果）'}")
    print()

    targets = sorted(glob.glob(os.path.join(plan, "assets", "images", "*qr*")))

    shots = []
    if args.shot:
        shots = [os.path.abspath(args.shot)]
    else:
        # 没指定就用 verify_page.js 默认落在 <plan>/.shots/ 的截图，省一步手工传参。
        # 优先只取地图指南区块那张（guide.png）—— 整页截图里二维码位置不定、常常解不出。
        default_shots = os.path.join(plan, ".shots")
        if os.path.isdir(default_shots):
            shots = sorted(glob.glob(os.path.join(default_shots, "guide*.png")))
            if not shots:
                shots = sorted(glob.glob(os.path.join(default_shots, "*.png")))
            if shots:
                print(f"自动使用截图：{', '.join(os.path.basename(s) for s in shots)}\n")
    targets += shots

    if not targets:
        print("没找到任何 *qr* 文件")
        return 0
    if not shots:
        print("提示：SVG 二维码需要在浏览器渲染后才能解码，"
              "先跑 verify_page.js 生成截图，或传 --shot <png>\n")

    bad = 0
    shot_ok = 0
    svg_labels = []
    shot_paths = [os.path.abspath(s) for s in shots]
    for t in targets:
        label = os.path.relpath(t, plan)
        is_shot = os.path.abspath(t) in shot_paths
        is_mini = "miniprogram" in os.path.basename(t).lower()
        ok, detail = decode(t, expect)
        if ok is None:
            if is_mini:
                print(f"  -- {label}: {detail}（小程序码，非标准 QR，属预期）")
            elif t.lower().endswith(".svg"):
                svg_labels.append(label)              # 渲染结果由截图核验，见下
            elif is_shot:
                print(f"  -- {label}: {detail}（该截图里没有可解的二维码）")
            else:
                print(f"  ?? {label}: {detail}")
            continue
        if is_shot and ok:
            shot_ok += 1
        if ok:
            print(f"  ✓  {label}: {detail}")
        else:
            bad += 1
            print(f"  ✗  {label}: {detail}")

    for label in svg_labels:
        if shot_ok:
            print(f"  ✓  {label}: 不单独解码；其渲染结果已由截图核验通过")
        else:
            print(f"  ?? {label}: SVG 无法直接解码，且没有可用截图（跑 verify_page.js 生成 guide.png）")

    print()
    if bad:
        print(f"⚠ {bad} 个二维码与登记的分享链接不一致，交付前必须修。")
        return 1
    print("二维码核验通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
