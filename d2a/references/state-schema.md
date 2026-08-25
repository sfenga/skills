# 工作区与状态契约

执行初始化、查看状态、恢复流程或修改状态前读取本文件。

## 工作区边界

所有生成产物必须位于 `<项目根目录>/.d2a`。初始化不得写入其他位置。
项目根目录优先使用显式传入的 `--root`，其次使用 Git 根目录，最后使用当前目录。

## 状态文件

- `config.json`：结构版本、项目绝对路径、项目名和创建时间。
- `state.json`：当前阶段与步骤、问题进度、已完成阶段、下一阶段和更新时间。
- `history.jsonl`：只追加的初始化与阶段完成事件。
- `qa/<阶段>.json`：对齐后的原子问题；`qa/<阶段>.jsonl`：逐题答案、判定、解释与理解度评分。

状态只能由确定性辅助脚本修改。除非已经说明损坏原因并执行修复，否则不要手工编辑。

## 阶段顺序

1. `architecture-01-boundary`
2. `architecture-02-runtime-driver`
3. `architecture-03-core-objects`
4. `architecture-04-state-evolution`
5. `architecture-05-module-cooperation`
6. `architecture-06-constraints-tradeoffs`
7. `architecture-99-code-map`
8. `architecture-07-overview`
9. `architecture-challenge`
10. `mini-scope`
11. `mini-design`
12. `mini-build`
13. `mini-test`
14. `report`
15. `complete`

`advance --expect` 提供乐观并发保护：如果读取状态后，其他进程或用户已经推进阶段，
当前操作必须停止。它还要求当前步骤为 `stage-ready`，并且必须在用户确认下一动作后传入
`--confirmed`。

## 阶段内步骤

- S1 至 S7：`atomic-question-alignment` → `analysis-generation` →
  `confirmation-questions`（4 题）→ `stage-ready`。
- S99：`analysis-generation` → `stage-ready`。
- 架构质疑：`challenge-preparation` → `challenge-dialogue`（6 轮）→
  `challenge-summary` → 可选 `review-required` → `stage-ready`。
- Mini 四阶段：`analysis-generation` → `confirmation-questions`（4 题）→ `stage-ready`。
- 报告：通过全部严格门禁后生成三个报告文件并进入 `complete`。

## 待完成标记

生成的工作产物包含 `<!-- d2a:pending -->`。只有当阶段已经包含项目特定内容和真实
代码证据时才能删除。报告的严格检查会拒绝仍带此标记的产物。
