# CONTRIBUTING

这个仓库只有一条硬要求：**改规范必须同步改校验。**

## 为什么

`verify_page.js` 的期望值来自被校验计划的 `manifest.json`，而检查项本身编码了 `SKILL.md` 里的硬约束。举例：

- `SKILL.md` 说「窄屏下多列时刻表必须横向滚动，不许压缩列宽」→ `verify_page.js` 第 6b 节断言 375px 下这些表**必须溢出容器**（装得下就说明列被压扁了）。
- `SKILL.md` 说「页面不得出现暴露未完成感的表述」→ 第 9 节扫描 `告诉我`／`暂按`／`示例窗口`／`待确认事项`／`同步更新` 等关键词。

所以只改 `SKILL.md` 不改脚本，会出现两种坏结果之一：老计划的检查继续按旧标准判通过（规范形同虚设），或者脚本开始对新计划误报（有人干脆关掉检查）。

## 改一条规则的标准动作

1. 先确认它属于哪一层：
   - 会影响**所有计划**的硬约束 → 写进对应的 `SKILL.md`（场景规范），必要时在 `AGENTS.md` 第 3 节内联最易漏的一条
   - 只影响**某个计划**的联动（某条路线会改写表格内容）→ 在该计划的 `_build/` 里写补充脚本，**不要塞进通用脚本**
2. 改 `SKILL.md`。
3. **同步改 `verify_page.js`**，把新规则变成可判定的断言。
4. 在 `examples/` 的样例上跑通，确认 0 失败。
5. 提交信息里写明：改了哪条规则、断言怎么变、样例是否仍全绿。

## 不要做的事

- **不要把某个计划的 DOM 结构或字段名硬编码进通用脚本。** 各计划的 `data-b` 键名不统一（一个用 `lodge`、另一个用 `stay`），脚本按别名表探测；新计划用了新键名，往 `FIELD_MAP` 里加别名，而不是改判断逻辑。
- **不要写同义反复的断言。** 曾经有「表格未被压缩」的检查是拿表宽和它自己的 `min-width` 比——永远通过，等于没测。要断言的是**设计意图**。
- **不要用「高度 ÷ 行高」数渲染行数。** 单元格里的 `.tag` 徽标 `line-height` 会把行框撑高，据此会误判成折行。用 `Range.getClientRects()` 的 `top` 去重。
- **不要在两处写同一条规则。** 见上。

## 加一个新计划类型的支持

`travel-workspace/SKILL.md` 定义了计划目录结构与 `manifest.json` 字段。新增字段时：

1. 在 `SKILL.md` 的字段表里补一行（含用途与是否必填）
2. 若页面要展示它，在 `verify_page.js` 的 `FIELD_MAP` 里给这个 manifest 字段配上页面 `data-b` 的别名
3. 在 `examples/` 的样例 `manifest.json` 里填上，确保检查真的跑到

## 依赖

- Python：`pip install -r requirements.txt`（fontTools / zxing-cpp / Pillow）
- Node：`npm install`（playwright-core），另需本机 Chromium：
  `npx playwright install chromium`

`python .agents/scripts/check_env.py` 会逐项告诉你缺什么；缺的部分会在交付里被标为「未执行的检查」，所以本地开发建议装齐。

## 提交前

```bash
python .agents/scripts/check_env.py
python .agents/scripts/subset_fonts.py examples/demo-harbin-3d
node   .agents/scripts/verify_page.js  examples/demo-harbin-3d
```

样例必须 0 失败。如果失败的是「脚本自身出错」，改脚本适配，**不要改样例去迁就脚本**。
