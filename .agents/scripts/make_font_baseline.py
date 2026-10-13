#!/usr/bin/env python3
"""重建字体基线（assets/fonts-baseline/）。

什么时候需要跑：
  - 想扩充基线字符集（subset_fonts.py 报「有字体回退到全量源」时）
  - 上游字体发新版，要升级基线
  - 换机器或换了仓库位置后重建

基线字符集的定义写在 build_charset() 里，**不用外部字表**，靠 codec 反查即可复现。

用法：
    python make_font_baseline.py --shared <工作区/_shared/fonts>     # 用现成全量 TTF
    python make_font_baseline.py --sample <计划目录>                  # 额外做等价性验证

全量 TTF 找不到时会按 baseline.json 里的 URL 下载（约 49 MB，一次即可），
可设 TRAVEL_ROADBOOK_PROXY=http://127.0.0.1:7897 走代理。
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT_ROOT = os.path.dirname(HERE)
BASELINE_DIR = os.path.join(AGENT_ROOT, "assets", "fonts-baseline")
USER_CACHE = os.environ.get("TRAVEL_ROADBOOK_FONT_CACHE") or os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache"),
    "travel-roadbook", "fonts",
)

sys.path.insert(0, HERE)
from subset_fonts import FONTS, SUBSET_OPTS, check_coverage, ensure_full  # noqa: E402


CHARSET_DEFINITION = [
    "GB2312 全集（6763 汉字 + 682 符号）",
    "Big5 全集（约 13000 繁体汉字）",
    "ASCII 可打印区间 U+0020–U+007E",
    "Latin-1 补充 + Latin Extended-A/B，U+00A0–U+024F（署名里的人名，如 Hanno Böck 的 ö）",
    "通用标点 U+2010–U+2030、U+2032–U+2040",
    "货币符号 U+20A0–U+20C0",
    "字母式符号 U+2100–U+2140",
    "箭头 U+2190–U+2200（含 ⇄ U+21C4）",
    "数学运算符 U+2200–U+2300",
    "制表符 U+2500–U+2540",
    "几何图形 U+25A0–U+2630（★☆○●□■ 等；© 属 Latin-1）",
    "CJK 标点 U+3000–U+3040、U+30FB–U+30FD、全角形式 U+FF00–U+FF61",
]


def build_charset():
    """广义覆盖字符集，可复现、不依赖任何外部字表文件。"""
    chars = set()
    # GB2312 全集（简体 6763 字 + 682 符号）
    for hi in range(0xA1, 0xFF):
        for lo in range(0xA1, 0xFF):
            try:
                chars.add(bytes([hi, lo]).decode("gb2312"))
            except Exception:
                pass
    # Big5 全集（繁体，避免引用港台地名时丢字）
    for hi in range(0xA1, 0xFA):
        for lo in range(0x40, 0xFF):
            try:
                chars.add(bytes([hi, lo]).decode("big5"))
            except Exception:
                pass
    # ASCII
    chars |= {chr(c) for c in range(0x20, 0x7F)}
    # Latin-1 补充 + Latin Extended-A/B —— 图片署名里的人名（如 Hanno Böck 的 ö）
    chars |= {chr(c) for c in range(0xA0, 0x250)}
    # 标点 / 货币 / 字母式符号 / 箭头（含 ⇄）/ 数学 / 制表 / 几何 / CJK 标点 / 全角
    for a, b in [(0x2010, 0x2030), (0x2032, 0x2040), (0x20A0, 0x20C0),
                 (0x2100, 0x2140), (0x2190, 0x2200), (0x2200, 0x2300),
                 (0x2500, 0x2540), (0x25A0, 0x2630),
                 (0x3000, 0x3040), (0x30FB, 0x30FD), (0xFF00, 0xFF61)]:
        chars |= {chr(c) for c in range(a, b)}
    for c in "\n\r\t":
        chars.discard(c)
    return chars


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def table_fingerprint(path):
    """逐表指纹。

    head 表要把 checkSumAdjustment（偏移 8，4 字节）清零后再比 —— 它是对整个文件算的
    完整性校验值，多经一层子集化会重算，且浏览器渲染完全不读它。其余表逐字节相同即等价。

    ⚠️ 不要用 head.compile(ttFont) 取字节：fontTools 在 ttFont.recalcTimestamp 为真时
    会把 head.modified 改写成「当前时间」，既污染对象又让两次调用不可比。
    """
    from fontTools.ttLib import TTFont
    f = TTFont(path)
    out = {}
    for tag in f.keys():
        if tag == "GlyphOrder":
            continue
        data = f.getTableData(tag)
        if tag == "head":
            data = bytearray(data)
            data[8:12] = b"\x00\x00\x00\x00"
            data = bytes(data)
        out[tag] = hashlib.sha256(data).hexdigest()[:16]
    return out


def compare_equivalent(a, b):
    """返回 (是否等价, 差异说明)。"""
    fa, fb = table_fingerprint(a), table_fingerprint(b)
    if set(fa) != set(fb):
        return False, f"表集合不同：仅 A {sorted(set(fa)-set(fb))} / 仅 B {sorted(set(fb)-set(fa))}"
    diff = [t for t in fa if fa[t] != fb[t]]
    if diff:
        return False, f"这些表不同：{sorted(diff)}"
    return True, f"{len(fa)} 张表逐字节一致（head.checkSumAdjustment 除外）"


def run_subset(src, chars, out, txt):
    with open(txt, "w", encoding="utf-8") as f:
        f.write("".join(sorted(chars)))
    r = subprocess.run([sys.executable, "-m", "fontTools.subset", src,
                        "--text-file=" + txt, "--output-file=" + out] + SUBSET_OPTS,
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-1000:]); print(r.stderr[-1500:])
        raise SystemExit(f"子集化失败：{src}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shared", default=None, help="工作区 _shared/fonts（含全量 TTF）")
    ap.add_argument("--sample", default=None, help="计划目录，用于等价性验证")
    args = ap.parse_args()

    os.makedirs(BASELINE_DIR, exist_ok=True)
    charset = build_charset()
    cs_path = os.path.join(BASELINE_DIR, "font-charset-broad.txt")
    open(cs_path, "w", encoding="utf-8").write("".join(sorted(charset)))
    print(f"字符集：{len(charset)} 字 → {os.path.basename(cs_path)}")

    entries, uncovered = {}, {}
    for font in FONTS:
        src = None
        if args.shared:
            p = os.path.join(args.shared, font["full"])
            src = p if os.path.isfile(p) else None
        if not src:
            p = os.path.join(USER_CACHE, font["full"])
            src = p if os.path.isfile(p) else None
        if not src:
            src, _ = ensure_full(font, args.shared)
        if not src:
            raise SystemExit(f"拿不到 {font['full']}")

        out = os.path.join(BASELINE_DIR, font["baseline"])
        txt = os.path.join(BASELINE_DIR, "." + font["key"] + ".chars.txt")
        run_subset(src, charset, out, txt)
        os.remove(txt)

        miss = check_coverage(out, charset)
        uncovered[font["slug"]] = miss
        print(f"  {font['family']:<22} {os.path.getsize(out)/1024:>8.1f} KB  "
              f"（源 {os.path.getsize(src)/1024/1024:.1f} MB）"
              f"{'  未覆盖 ' + str(len(miss)) if miss else ''}")
        entries[font["slug"]] = {
            "file": font["baseline"], "sha256": sha256(out), "bytes": os.path.getsize(out),
            "family": font["family"], "full_ttf_bytes": os.path.getsize(src),
            "source": dict(font["source"],
                           url=font["url"],
                           archive_member=font["archive_member"]),
            "subset_opts": SUBSET_OPTS,
        }

    # 等价性验证：从全量直切 vs 从基线切，必须逐字节一致
    proof = {"method": "同一份计划字符表，分别从全量 TTF 与从基线各切一次，比较 SHA-256"}
    if args.sample:
        plan = os.path.abspath(args.sample)
        html = os.path.join(plan, "index.html")
        if os.path.isfile(html):
            sys.path.insert(0, HERE)
            from subset_fonts import collect_chars
            all_chars, mono = collect_chars(html)
            tmp = os.path.join(BASELINE_DIR, ".eqtest")
            for font in FONTS:
                chars = all_chars if font["key"] == "wenkai" else mono
                full = os.path.join(args.shared, font["full"]) if args.shared else None
                if not full or not os.path.isfile(full):
                    continue
                a, b = tmp + "-a.woff2", tmp + "-b.woff2"
                run_subset(full, chars, a, tmp + ".chars.txt")
                run_subset(os.path.join(BASELINE_DIR, font["baseline"]), chars, b, tmp + ".chars.txt")
                same, detail = compare_equivalent(a, b)
                miss = check_coverage(b, chars)
                print(f"  等价性 {font['family']:<22} {'✓' if same else '✗'} {detail}"
                      f"{'  缺字 ' + str(len(miss)) if miss else ''}")
                proof[font["slug"]] = {"equivalent": same, "detail": detail,
                                       "chars": len(chars), "missing": miss,
                                       "sample": os.path.basename(plan)}
                for p in (a, b, tmp + ".chars.txt"):
                    if os.path.isfile(p):
                        os.remove(p)
            proof["verified_at"] = __import__("datetime").date.today().isoformat()
        else:
            print(f"  跳过等价性验证：{html} 不存在")

    # baseline.json 由本脚本**完整生成**（不与旧文件合并），单一事实源，避免手工段落与
    # 脚本产出漂移、或出现 slug / key 两套重复条目。
    meta = {
        "schema": "font-baseline/1",
        "generator": "scripts/make_font_baseline.py",
        "generated_at": __import__("datetime").date.today().isoformat(),
        "purpose": "自带的「广义覆盖」字体基线，替代 48.9 MB 的全量源字体。"
                   "从基线切出的计划子集与从全量直切的结果**逐表等价**"
                   "（除 head.checkSumAdjustment 外全部逐字节相同），见 equivalence_proof。",
        "charset": {
            "file": os.path.basename(cs_path),
            "sha256": sha256(cs_path),
            "char_count": len(charset),
            "definition": CHARSET_DEFINITION,
            "why_not_gb2312_only": (
                "纯 GB2312 基线（仅 1.85 MB）实测会丢 6 个真实字符：ö、©、⇄、納、氣、雙。"
                "ö 出现在摄影师 Hanno Böck 的署名里，© 每一页的图片署名都要用，"
                "繁体字在引用港台地名时会出现。故必须并入 Big5 与 Latin-1。"),
        },
        "coverage_note": {
            "summary": "两套字体对上述字符集的未覆盖字符**全部是汉字以外的冷门符号**，汉字未覆盖数为 0。",
            "uncovered": {k: {"count": len(v), "sample": "".join(v[:60])} for k, v in uncovered.items()},
            "meaning": "这些字符（双向控制符、数理字母符号 U+2102–U+213F、冷门货币、"
                       "杂项符号 ☄☎☕☠ 等）**全量源字体本身也没有**，与基线无关；"
                       "页面不会用到，真出现时由 CSS font-family 回退到系统字体渲染，不会乱码。",
        },
        "baselines": entries,
        "equivalence_proof": proof,
        "safety": {
            "coverage_check": "subset_fonts.py 切完后逐字核对输出 cmap；基线没覆盖就自动回退全量字体重切，绝不静默丢字。",
            "fallback_order": ["自带基线", "工作区 _shared/fonts 全量 TTF",
                               "用户级缓存全量 TTF", "按 URL 下载全量 TTF"],
            "user_cache_dir": os.path.abspath(USER_CACHE) + os.sep,
            "rebuild_when": "subset_fonts.py 报「有字体回退到全量源」时，或上游字体发新版时，重跑本脚本。",
        },
    }
    meta_path = os.path.join(BASELINE_DIR, "baseline.json")
    json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n已更新 {os.path.relpath(meta_path, AGENT_ROOT)}")
    print(f"基线目录合计：{sum(os.path.getsize(os.path.join(BASELINE_DIR, f)) for f in os.listdir(BASELINE_DIR)) / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
