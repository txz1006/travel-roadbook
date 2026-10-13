---
name: travel-workspace
description: 旅行路书 agent 的工作区初始化与成果归档规范。在每个旅行计划开工前使用：在当前工作目录建立并维护数据目录（默认「旅行计划/」）容器，读取其中的 AGENTS.md 索引，判断是新建计划还是更新既有计划；并在环境提供地图指南能力时创建指南与二维码。触发场景：用户提出任何旅行规划需求、要求生成路书/HTML、要求修改既有行程。
---

# 旅行计划工作区

本技能定义「旅伴」agent 的**工作区初始化**与**成果归档**规范。目标是让它具备跨会话记忆：不重复劳动、不重复创建地图指南、能复用已有素材。

**在开始任何旅行规划工作前执行第一、二节。** 纯问答（问某个景点开放时间之类）不需要初始化。

---

## 一、先读容器

工作区容器固定为：

```
<当前工作空间>/旅行计划/
```

**第一步永远是读 `旅行计划/AGENTS.md`**：

- **存在** → 读取后按其中的索引与约定工作。
- **不存在** → 走第二节初始化。注意：容器可能不存在但工作区里已有产物（如根目录躺着一个 `<目的地>-<N>d/` 目录），**这种情况要先问用户是否迁入，不要静默搬运。**

初始化与后续维护都**只写工作目录**。**绝不写入 `.agents/`**——那是 agent 定义（规范、脚本、字体基线），不是用户数据。

---

## 二、初始化容器（幂等）

首次在某工作区工作时建立：

```
旅行计划/
├── AGENTS.md            ← 引导文档，见第三节
├── _shared/README.md   ← 跨计划共用素材说明
├── _shared/fonts/      ← 【可选】全量源字体 TTF + OFL 许可，只在基线覆盖不足时才需要
└── _build/             ← 该计划专属的补充脚本与暂存文件
```

**字体默认不需要 `_shared/fonts/`。** 工具脚本与 6.7 MB 的字体基线都随仓库自带（见第六节），新工作区开箱即用、0 字节下载。`_shared/fonts/` 只在两种情况下才建立：① 基线覆盖不到某个字符、需要回退全量字体；② 要重建基线。**不要为了"以防万一"预先下载 48.9 MB 的源字体。**

**幂等要求**：已存在的文件一律不覆盖，只补缺失的。`AGENTS.md` 若已存在，**只追加索引行或修正已有行**，不整份重写（用户可能手工改过）。

---

## 三、AGENTS.md 必备结构

初始化时按这个结构生成：

1. **这个目录是什么** — 容器用途，以及"为什么需要它"（agent 本身无状态）
2. **三条硬规则** — ①产出前先读本文件 ②不写 `.agents/`（那是 agent 定义）③`manifest.json` 是唯一事实源
3. **目录约定** — 命名规则 + 每个文件职责
4. **计划索引** — 表格：计划 ID / 目的地 / 日期 / 人数 / 人均预算 / 状态 / 地图指南 ID
5. **新建计划流程** — 编号步骤
6. **地图指南** — 默认自动创建、能力探测、幂等要求
7. **更新既有计划流程**
8. **禁止事项**

### 命名规则

**计划 ID：`<YYYY-MM>-<目的地 slug>-<N>d`**，例如 `2026-10-chengdu-jiuzhaigou-7d`。

- **ASCII 小写 + 连字符**。不要用中文目录名——curl 长路径、PowerShell 字面量在中文路径上有编码坑，而计划 ID 是机器处理最多的字段。
- slug 用拼音或英文；多目的地用 `-` 连接；同月同目的地重复加序号 `-2`。

### 每个计划的文件

| 文件 | 内容 |
|---|---|
| `manifest.json` | 结构化元数据，**唯一事实源**（见第四节） |
| `plan.md` | 方案摘要 + 关键决策理由 + 变更日志。**不复制逐日表格** |
| `sources.md` | 来源链接 + 查询日期 + 已核实/估算/待确认三分 |
| `index.html` | 交互式路书，**完整行程的唯一载体**，自包含离线可开 |
| `assets/` | 该计划专属资源（images / fonts / credits.json） |

---

## 四、manifest.json 字段

```json
{
  "schema": "travel-plan/1",
  "plan_id": "<目录名>",
  "title": "…",
  "status": "草稿 | 已确认 | 出行中 | 已完成 | 已放弃",
  "created_at": "YYYY-MM-DD",
  "updated_at": "YYYY-MM-DD",
  "trip": {
    "origin": "…", "destinations": ["…"],
    "season": "…",
    "dates": { "type": "placeholder | confirmed", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "note": "…" },
    "days": 7, "nights": 6,
    "party": { "total": 4, "elders": 2 },
    "planning_mode": "通用 | MBTI 适配",
    "lodging_bases": [{ "city": "…", "area": "…", "nights": 2, "nights_at": ["D1", "D6"] }]
  },
  "budget": { "currency": "CNY", "party_size": 4, "rooms": 2,
    "includes_round_trip_flight": true, "active_tier": "comfort",
    "tiers": { "…": { "per_night": {…}, "total_range": [..], "per_person_range": [..] } },
    "user_stated_ceiling_per_person": 8000,
    "toggles_in_page": ["…"] },
  "deliverables": { "html": "index.html", "assets_dir": "assets/", "offline_ok": true },
  "map_guide": { "provider": "tencent-map-guide", "travel_guide_id": "…",
    "share_url": "…", "guide_slug": "…", "dates_embedded": ["…"], "created_at": "…",
    "update_policy": "改日期或点位走 update，不要再 create" },
  "facts": { "verified": ["…"], "estimated": ["…"], "tbd": ["…"] },
  "known_risks": ["…"]
}
```

**`origin` 字段**：写用户明确说出的**出发城市**。用户拒绝提供、只能做区域级估算时，写区域并标注，例如 `华东（区域级粗估，出发点待确认）`——不要替用户填一个具体城市。

**隐私红线**：只记「需要哪些证件」，**不记证件号码、护照号、身份信息**。

---

## 五、开工前必做的两项检查

### 1. 查有没有既有计划

读 `AGENTS.md` 索引。**同目的地 + 同档期已有计划 → 走更新流程，不要另起一份。** 重复计划会导致重复地图指南和素材冗余。

### 2. 字体：直接跑脚本，别下载任何东西

仓库自带 6.7 MB 的「广义覆盖」字体基线，**换工作区、换机器都不用下载字体**：

```bash
python .agents/scripts/subset_fonts.py "<计划目录>"
```

脚本自己会按「自带基线 → `_shared/fonts` 全量 → 用户级缓存 → 按 URL 下载」的顺序找字源，默认路径下 **0 字节网络流量**。产物是两个 `*.woff2`（约 218 KB + 21 KB），写进该计划自己的 `assets/fonts/`——**不要跨计划引用 `_shared`**，交付包必须自包含。

三条要点：

- **不要预先下载 48.9 MB 的源字体**。只有脚本报告「有字体回退到全量源」时才需要，见第六节。
- **文案一改就要重跑**（`@font-face` 引用的子集按实际用字裁剪，不重跑新字会落进回退字体）。
- 脚本切完会逐字核对覆盖，缺字自动回退全量重切，**不会静默丢字**；连全量字体都没有的字符会列出来（浏览器按 `font-family` 回退到系统字体，不会乱码）。

---

## 六、工具脚本与字体基线（仓库自带，开箱即用）

`.agents/scripts/` 与 `.agents/assets/fonts-baseline/` 解决了「每个新工作区都要重新下载 48.9 MB 字体」的问题。详细说明见 `.agents/scripts/README.md`，这里只列要点。

```
.agents/
├── scripts/
│   ├── check_env.py           ← 环境预检：本机缺什么、哪几项检查将不执行
│   ├── subset_fonts.py        ← 从基线切出计划字体子集（含覆盖校验 + 自动回退）
│   ├── verify_page.js         ← 浏览器端回归校验，期望值自动读 manifest.json
│   ├── decode_qr.py           ← 解码二维码核验指向
│   └── make_font_baseline.py  ← 重建字体基线
└── assets/fonts-baseline/
    ├── wenkai-broad.woff2     ← 4.5 MB（替代 23.4 MB 全量）
    ├── sarasa-broad.woff2     ← 2.3 MB（替代 24.4 MB 全量）
    ├── font-charset-broad.txt ← 17,365 字覆盖集
    ├── baseline.json          ← 源版本、哈希、等价性证明
    └── OFL-*.txt              ← 两套字体的 OFL 许可
```

**等价性**：从基线切出的子集与从全量字体直切的结果**逐表等价**（除 `head.checkSumAdjustment` 外逐字节相同，实测同一字符表下 woff2 的 SHA-256 完全一致）。**不要**因为担心质量而在默认流程里改用全量字体。

**基线覆盖集**（17,365 字）＝ GB2312 全集 ∪ Big5 全集 ∪ Latin-1/Ext-A ∪ 标点箭头货币符号。并入 Big5 与 Latin-1 是**必须的**：纯 GB2312 会丢 `ö`（摄影师署名里的）、`©`（每页图片署名都用）、`⇄`（路线备选标签）与繁体字。

**回退**：脚本切完逐字核对输出 cmap；基线没覆盖就自动回退全量字体重切（打印 `! 基线缺 N 字 …` 与 `已回退`），**绝不静默丢字**。打印 `⚠ 有字体回退到全量源` 说明基线该扩充了 —— 在 `make_font_baseline.py` 的 `build_charset()` 里补码位区间后重建基线，并确认 `baseline.json` 的 `equivalence_proof` 全部 `equivalent: true`。

运行环境：`subset_fonts.py` / `decode_qr.py` / `make_font_baseline.py` 需要带 `fontTools`、`zxing-cpp`、`Pillow` 的 Python（`pip install -r requirements.txt`）；`verify_page.js` 需要 `playwright-core` 与本机 Chromium（`npm install && npx playwright install chromium`）。**先跑 `python .agents/scripts/check_env.py`**——它会逐项报告本机缺什么、因缺依赖哪几项检查将不执行，照它的结论在交付里如实交代。

### 交付前必跑的三件

1. `python .agents/scripts/subset_fonts.py <计划>` —— 文案改过就必须重跑
2. `node .agents/scripts/verify_page.js <计划>` —— 通用回归；**计划特有的联动**（某条路线会改写表格内容之类）需在该计划 `_build/` 里另写补充脚本
3. 嵌了二维码就 `python .agents/scripts/decode_qr.py <计划>` —— 从源文件解一次，再从页面截图解一次

`verify_page.js` 的期望值全部从 `manifest.json` 读（`trip.days`、`budget.tiers[*]` 的四个金额、`map_guide.share_url`），所以换计划不用改脚本。它还会**自动发现切换组**：任何一组共享 `data-*` 且带 `aria-pressed` 的按钮都会被逐个点击、断言单选、断言切换确实改变了页面内容。

---

## 七、地图指南（可选能力）

交付 `index.html` 时，**若环境提供地图指南能力**，就为该计划创建一份指南，并把分享链接转成二维码嵌入页面。下面的操作细节以腾讯地图指南为例；换用其他地图服务时，按同一套约束执行（**幂等、点位密度、二维码必须解码核验**），接口字段以该服务的规格文档为准。

### 能力探测与降级

**先用一个无副作用的轻量调用当探针**（例如读取规格文档，返回小、不写数据）。探测失败，或环境根本不提供这个能力，就**静默跳过整个地图指南环节**：不影响 HTML 交付，不中断，也不向用户报错或抱怨缺能力。

建指南与查 POI 往往是**两个独立能力**：探针通过不等于 POI 检索可用，要分别确认。缺 POI 检索时改用坐标点（见「已知坑」）。

### 幂等（最重要）

- `guide_slug` 用**计划 ID**（如 `2026-12-harbin-3d`）。重复创建会返回原指南 ID，不会在用户账号里堆重复指南。
- 创建后**必须把 `travel_guide_id` 写回 `manifest.json`**。
- 之后改日期、改点位一律走**更新**，不要再创建。

### 日期

指南把日期编码在每个分组的日期扩展字段里。用户日期未定时用合理示例窗口，**页面正文不解释这件事**（详见 `travel-story-preview/SKILL.md` 第七节「页面是交付物，不是对话窗口」），把占位说明写在交付消息里对用户说。日期确定后更新指南——**分享链接与二维码不变**。

### 点位密度

**每天 2–3 个锚点即可（整份约 10–12 个）**，不要复刻整张行程表。地图指南的用途是在路上导航，不是替代路书。

### 已知坑

- **创建的返回值极大**（实测约 10 万字符，含完整回填数据），会超工具输出上限、被落盘到临时文件。**用脚本解析该文件取 `travel_guide_id` 与分享链接，不要整段读进上下文。**
- 规格文档与创建接口的版本可能不一致（文档停在旧结构，接口要求新结构）。**两者结构完全不同，以工具运行时 schema 为准，不要照旧文档拼参数。**
- 跨组复用同一 POI 时，同 `element_id` 内容必须完全一致；给同一 POI 在两天各写一份时，**用不同 `element_id` 更省事**。
- 互为备选靠**同位次**表达（仅同类型之间合法）。
- 查 POI 时注意同名歧义：搜「中央大街」会先返回其他县市的同名道路，要按省市区筛选后取正确的实体。

### 二维码

- **URL 二维码**：本地生成即可（离线、无依赖），用 SVG 便于印刷。生成后**必须实际解码校验**能还原出正确链接——用解码库读一遍，或解码从页面截取的二维码，不要只看"长得像"。
- **微信小程序码**：由接口 `need_miniprogram_qrcode: true` 返回（base64 PNG），存为 `assets/images/` 下的资源。注意它是微信专有格式，通用解码库识别不了，属正常，不要误判为损坏。
- 页面上两个码要**分别标注用途**（浏览器扫码 / 微信扫码）。二维码区块在打印态应保留。

---

## 八、收尾：回填索引

每次产出或更新后：

1. 更新该计划的 `manifest.json`（含 `updated_at`）
2. 在 `AGENTS.md` 索引表**追加或修正**对应行
3. 若产生了可跨计划复用的素材，放进 `_shared/` 并在 `_shared/README.md` 补一行（**先确认许可允许再分发**）
