# 工具脚本

旅行路书交付链路的可复用工具。**所有脚本的产物都落在工作目录的数据目录里，本目录只放脚本与只读资源，绝不写用户数据。**

## 一次说清：字体为什么不用再下载

| | 体积 |
|---|---|
| 全量源字体（霞鹜文楷 Screen + 更纱黑体 Mono SC） | 48.9 MB |
| 仓库自带的「广义覆盖」基线 | **6.7 MB** |
| 每个计划实际交付的子集 | 213 KB + 21 KB |

基线放在 `assets/fonts-baseline/`，随仓库走，换工作区、换机器都不用重新下载。每个计划仍单独出一个极小的子集，保证页面离线自包含。

**等价性**：从基线切出的子集与从全量字体直切的结果**逐表等价**（除 `head.checkSumAdjustment` 这一个文件完整性校验值外全部逐字节相同；该字段浏览器渲染不读）。实测同一份计划字符表，两条路径产出的 woff2 **SHA-256 完全相同**。证据见 `assets/fonts-baseline/baseline.json`。

**安全兜底**：`subset_fonts.py` 切完会逐字核对输出 cmap。如果基线没覆盖某个字符（例如韩文谚文、CJK 扩展 A 区），自动回退到全量字体重切，**绝不静默丢字**；连全量字体都没有的字符会明确列出来（这类字符浏览器会按 `font-family` 回退到系统字体渲染，不会乱码）。

## 脚本清单

| 脚本 | 作用 | 何时用 |
|---|---|---|
| `check_env.py` | 环境预检：本机缺什么、哪几项检查将不执行 | 开工前，以及交付前交代「哪些检查没跑」 |
| `subset_fonts.py` | 从基线切出计划专属字体子集 | 每次生成/更新 `index.html` 后（文案改过就必须重跑） |
| `verify_page.js` | 浏览器端全量回归校验（50 余项） | 每次交付 HTML 前 |
| `decode_qr.py` | 解码二维码，核对是否指向登记的分享链接 | 嵌了地图指南二维码后 |
| `make_font_baseline.py` | 重建字体基线 | 基线覆盖不足、上游字体升级、换机器重建 |

## 用法

先装依赖并自检：

```bash
pip install -r requirements.txt            # fontTools / zxing-cpp / Pillow
npm install && npx playwright install chromium   # verify_page.js 需要

python .agents/scripts/check_env.py        # 逐项告诉你缺什么、哪几项检查将不执行
```

齐了之后，在任意计划目录上跑：

```bash
PLAN="<工作目录>/旅行计划/<计划ID>"

# 1) 字体子集（默认走自带基线，0 字节网络流量）
python .agents/scripts/subset_fonts.py "$PLAN"

# 2) 页面回归校验（期望值自动从 manifest.json 读）
#    截图落在 $PLAN/.shots/：desktop.png / mobile.png / guide.png
#    guide.png 是地图指南区块的元素截图，专门留给第 3 步解码用
node .agents/scripts/verify_page.js "$PLAN" --shots "$PLAN/.shots"

# 3) 二维码核验（不传 --shot 时会自动取 .shots/guide.png）
python .agents/scripts/decode_qr.py "$PLAN"

# 4) 只有需要时才重建基线
python .agents/scripts/make_font_baseline.py \
      --shared "<工作目录>/旅行计划/_shared/fonts" \
      --sample "$PLAN"
```

`verify_page.js` 找不到 Chromium 时会明确提示装浏览器，也可以用 `ROADBOOK_CHROME=<可执行文件路径>` 指定；字体缓存目录可用 `TRAVEL_ROADBOOK_FONT_CACHE` 覆盖。

### `subset_fonts.py` 选项

- `--strict`：优先用全量 TTF 而不是基线。结果等价，只是慢，用于排查基线问题。
- `--shared DIR`：指定 `_shared/fonts`。默认从计划目录向上最多 4 层自动查找。

### `verify_page.js` 检查什么（51 项左右，随页面结构浮动）

期望值全部来自 `manifest.json`，不写死在脚本里，所以换计划不用改脚本：

- `trip.days` → 日期标签数量
- `budget.tiers[*]` 的金额字段 → 各档住宿切换后的数字（见下方「字段别名」）
- `map_guide.share_url` → 页面正文必须出现

以及这些不依赖期望值的通用检查：

1. 两个字体子集是否加载成功
2. 日期标签：逐个点击，每次只显示一个面板且 `aria-selected` 正确
3. 全部图片加载成功；**目录里不能有下载了却不引用的实景照片**（二维码 PNG 属有意保留的转发素材，豁免）
4. 预算三档联动 + 档位按钮单选性
5. **切换组自动发现**：任何一组共享 `data-*` 且带 `aria-pressed` 的按钮（路线二选一、进沟与否…）都会自动被测试——逐个点击、断言单选、断言切换确实改变了页面内容。这样不必为每种新联动单独写测试。
6. 清单：勾选、刷新后保持（localStorage）、只看未完成、清空
7. 320 / 375 / 414 / 768 / 1024 / 1280 px 六档宽度无横向溢出
8. **宽表格不压缩列宽**：窄屏下多列时刻表必须**溢出容器**（装得下就说明列被压扁了）、「时段」列与第三列表头必须单行渲染。判定行数用 Range 的客户端矩形按视觉行数，不要用「高度 ÷ 行高」——单元格里的 `.tag` 徽标 `line-height:1.6` 会撑高行框造成误判。
9. 打印态：所有日面板展开、日期标签栏隐藏
10. **交付物口径扫描**：页面正文不得出现 `告诉我`、`暂按`、`示例窗口`、`待确认事项`、`同步更新`、`二维码不变` 等「这份文档还没做完、以后还会改」的表述。命中会连上下文一起打印。**注意 `待确认` 这个核验状态标签是允许的**（它标注的是外部票价/班次的浮动，不是文档状态），被禁的只是 `待确认事项` 这类标题。
11. 控制台零错误、零资源加载失败

#### 字段别名（为什么换计划不用改脚本）

各计划的 `data-b` 键名和 `manifest.json` 字段名并不统一（一个用 `lodge`、另一个用 `stay`；一个有 `total_with_buffer`、另一个只有 `total_range`）。脚本按别名表探测，**manifest 里没有的字段、或页面上没有对应键的，跳过并打印说明，不算失败**——避免用甲的假设去判乙。

| manifest 字段 | 页面 `data-b` 别名的优先级 |
|---|---|
| `per_person_range` | `perhead` → `per_person` → `perperson` → `人均` |
| `total_with_buffer` / `total_range` | `total` → `总额` |
| `subtotal_range` | `subtotal` → `sub` → `分项` |
| `lodging_total` | `lodge` → `stay` → `lodging` → `住宿` |
| `buffer_range` | `buffer` → `机动` |

新计划如果用了别的键名，往 `verify_page.js` 的 `FIELD_MAP` 里加个别名即可。

**计划特有的联动**（例如某条路线会改写表格内容）不在此列，需在该计划的 `_build/` 里另写补充脚本。

## 什么时候需要重建基线

`subset_fonts.py` 如果打印「⚠ 有字体回退到全量源」，说明基线字符集不够用了。此时：

1. 在 `make_font_baseline.py` 的 `build_charset()` 里补上缺的码位区间；
2. 重跑 `make_font_baseline.py`（会自动重跑等价性验证并写回 `baseline.json`）；
3. 确认 `baseline.json` 里 `equivalence_proof` 两项都是 `equivalent: true`。

## 已知坑

- **不要把某一个计划的 DOM 结构或字段名硬编码进通用脚本**。第一版 `verify_page.js` 假设 `data-b="lodge"`，换到成都（用 `stay`）就直接崩了。现在改成别名表探测 + 缺字段跳过，并且**脚本自身出错时会明确说「脚本自身出错，不代表页面有问题」并给出出错行**，避免把维护者的问题误判成页面的问题。
- **数「渲染行数」不要用 `高度 ÷ 行高`**。单元格里的 `.tag` 徽标 `line-height:1.6` 会把行框撑高，据此算出「两行」，实测让「时段列折行」误报了 5 张表。改用 `Range.getClientRects()` 的 `top` 去重（4px 容差合并同一行）。
- **断言别写成同义反复**。第一版「表格未被压缩」是拿表宽和它自己的 `min-width` 比 —— 永远通过，等于没测。要断言的是**设计意图**：窄屏下宽表格必须「装不下」，装得下就说明列被压扁了。
- **测隐藏元素前先让它可见，并让页面重算**。日面板默认 `display:none`，那时算出的 `scrollWidth/clientWidth` 和 `is-scrollable` 全是陈旧值；展开后要派发一次 `resize` 触发重算，否则断言会基于过期状态（实测因此误报过一轮）。
- **不要在页面里写「这份文档还没做完」**。曾把「指南内日期暂按…示例窗口排，定了告诉我，我改过来，二维码不变」写进了交付页面。已列为硬约束并进了自动检查（第 9 节），见 `travel-story-preview/SKILL.md` 第七节。
- **向还不存在的目录写文件会失败**：`> 计划/_build/x.log` 在父目录不存在时报 `No such file or directory`（Windows 的 Git Bash 上尤其常见）。先 `mkdir -p` 再重定向。
- **`head.compile(ttFont)` 不是只读操作**：fontTools 在 `ttFont.recalcTimestamp` 为真时会把 `head.modified` 改成当前时间。比对字体时请直接读原始表字节（见 `make_font_baseline.py` 的 `table_fingerprint`）。
- **子集化是确定性的**：同一源 + 同一字符表 → 同一字节，可以放心用哈希比对。
- **微信小程序码不是标准 QR**，zxing 解不出属预期。
