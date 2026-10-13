# examples/demo-harbin-3d

一份**真实完成过**的 3 天行程，留在这里当格式参照，同时也是工具链的可运行夹具——任何改动规范或脚本的人，都应该能在它上面跑出 0 失败。

```bash
python .agents/scripts/subset_fonts.py examples/demo-harbin-3d
node   .agents/scripts/verify_page.js  examples/demo-harbin-3d
# → 51 通过 / 0 失败（第 8 项「地图指南分享链接」因样例无指南而跳过，属预期）
```

## 文件分工

| 文件 | 作用 |
|---|---|
| `manifest.json` | 结构化元数据，唯一事实源。`verify_page.js` 的期望值（天数、三档预算金额）全部从这里读 |
| `plan.md` | 方案摘要 + 关键决策理由 + 变更日志。**不复制逐日表格** |
| `sources.md` | 来源链接 + 查询日期 + 已核实/估算/待确认三分 |
| `index.html` | 交互路书，完整行程的唯一载体，离线可开 |
| `assets/images/` | 实景照片 + `credits.json`（作者、许可、原始条目、是否裁切） |
| `assets/fonts/` | `subset_fonts.py` 切出的字体子集 + 两份 OFL 许可 |

## 这个样例被刻意做小了

生产版每次交付按「首屏一张、每天至少一张」配图；本样例**只保留一张 CC0 照片**，其余章节无图。原因见 `NOTICE`：CC BY-SA / CC BY 的图片随仓库分发会给每个再分发者带来署名与相同方式共享的义务，而样例的职责只是演示格式。所以：

- 只剩一张 CC0 图（冰雪大世界的冰砌建筑，Garosio33 摄），首屏用它；
- 章节配图的 `<figure class="shot">` 结构被整体移除——**生产版要保留**，它是「每天一个视觉章节」的载体；
- `credits.json` 里那条记录就是每张图的登记格式，字段一个不少。

同理，本样例**没有创建地图指南**：开源仓库不该带任何个人账号的分享链接。因此 `manifest.json` 里没有 `map_guide` 区块，页面里也没有二维码区块。生产版在环境提供该能力时会写入 `travel_guide_id` 与 `share_url`，并跑 `decode_qr.py` 复核渲染后的二维码。

## 拿它当起点

```bash
cp -r examples/demo-harbin-3d 旅行计划/2027-01-<目的地slug>-<N>d
```

然后按 `AGENTS.md` 第 4 节改计划 ID、按新行程重写 `plan.md` 与 `sources.md`、按新内容重做页面。**改完文案必须重跑 `subset_fonts.py`**——子集是按实际用字裁的，不重跑新字会落进系统回退字体。
