# travel-roadbook

一个**与客户端无关**的旅行规划 agent：把一段自然语言的旅行意愿，变成可执行、可调整、预算透明的行程方案，以及一份可以离线打开、能发给同行朋友的图文交互路书。

它不是一个 prompt 片段，而是一套带**确定性验收标准**的工作流——规范文本负责「怎么做」，`verify_page.js` 的 50 余项回归负责「做没做到」。后者才是质量可复现的部分。

## 它解决什么

大多数「规划旅行」的 prompt 都能生成一份看起来合理的行程，难的是两件事：

- **不编造。** 开放时间、票价、班次、住宿价格要能追溯到来源与查询日期，查不到就老实标「待确认」，而不是填一个像真的数字。
- **产出物可用。** 一张 9:16 的图、一段 markdown 都不够——要能在零下二十度的路上打开、在手机窄屏上读、能打印、能分享。

所以这套东西的重心在**交付物规范与回归校验**，不在提示词技巧。

## 快速开始

```bash
git clone <this-repo> && cd travel-roadbook

# 1) 看本机哪些检查能跑（缺依赖会明确告诉你缺什么、哪几项检查将不执行）
python .agents/scripts/check_env.py

# 2) 依赖装齐后，在一份样例上跑通完整链路
python .agents/scripts/subset_fonts.py examples/demo-harbin-3d
node   .agents/scripts/verify_page.js  examples/demo-harbin-3d
```

然后把仓库根作为工作目录，对 agent 说：

> 我们 4 人想去哈尔滨玩 3 天，帮我排顺路行程、住宿区域和预算明细

**出发城市必须说。** 往返大交通通常占预算三到五成，也决定抵离日的实际可用时间；缺这一项 agent 会先问你，而不是替你假设一个城市。

## 支持哪些客户端

任何会读取仓库根 `AGENTS.md` 的客户端都能用——Claude Code、Codex、Cursor、Copilot、Gemini CLI、Windsurf 等。`AGENTS.md` 是唯一入口，它告诉你按什么顺序读其余规范。

| 客户端 | 需要做的事 |
|---|---|
| Codex / Cursor / Gemini CLI / opencode 等（扫 `.agents/skills/`） | 无，打开仓库即可 |
| Claude Code v2.1.277 及以后 | 无。它直接读仓库根的 `AGENTS.md`，也扫 `.agents/skills/` |
| Claude Code 更早版本，或团队里有人没升级 | 在 `CLAUDE.md` 里写一行 `@AGENTS.md` 导入 |

**别用「指路式」的 `CLAUDE.md`。** Anthropic 文档说明：只要存在 `CLAUDE.md`，Claude Code 默认就**不再直接读** `AGENTS.md`；而一句纯文字的指路（例如「规则见 AGENTS.md」）并不会触发读取——Claude 只会在它自己决定打开那个文件时才看到。所以要兼容旧版本就用 `@AGENTS.md` 导入，否则干脆不放这个文件。

**同理，不提交任何指向 `.agents/` 的软链。** 一是 Windows 上提交的软链在未开 `core.symlinks` 的克隆里会变成一个纯文本文件（等于把规则弄丢），二是 `.agents/skills/` 本身就是跨客户端约定目录，多数客户端会直接扫——重复一份只会带来漂移。万一你的客户端确实不认它，`AGENTS.md` 第 2 节里有显式指针，agent 照读即可。

## 目录结构

```
travel-roadbook/
├── AGENTS.md                    唯一入口：能力矩阵 · 必读顺序 · 内联硬规则
├── .agents/                     agent 的全部逻辑，与客户端无关
│   ├── agent.md                 完整角色与工作流
│   ├── skills/                  硬约束的唯一出处（跨客户端约定目录）
│   ├── scripts/                 环境预检 / 字体子集 / 页面回归 / 二维码核验
│   └── assets/fonts-baseline/   6.7 MB 字体基线，开箱零下载
├── examples/                    脱敏样例，可整体删除
└── 旅行计划/                     【不入仓】你的产出落在这里
```

## 几个设计取舍

**为什么字体基线要进仓库（6.7 MB）。** 页面要求离线自包含，中文排版又必须用指定字体（霞鹜文楷 Screen 排正文、更纱黑体 Mono SC 排数字）。基线是 48.9 MB 全量字体的广义覆盖压缩版，从它切出的子集与全量直切**逐表等价**（`baseline.json` 里有等价性证明）。入仓换来的是新工作区零下载，代价是仓库大 6.7 MB。

**为什么硬约束只写一份。** 「出发城市必答」「宽表格窄屏必须横向滚动」「HTML 是交付物不是对话窗口」这类规则，写两处就一定会在某次改动后漂移——而漂移的恰好是质量最依赖的部分。所以规则只在 `SKILL.md` 里定义，`AGENTS.md` 只内联最容易漏的几条。

**为什么 `verify_page.js` 是这套东西的核心。** 52 项检查里包含「页面不得出现『这份文档还没做完』的表述」这种口语化规则的可执行版本。规范文本靠自觉，回归脚本不靠自觉。

## 许可

代码 MIT。规范文本 CC BY 4.0。字体与样例图片的许可见 `NOTICE`。
