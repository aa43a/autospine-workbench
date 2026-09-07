# 检查开发集图层接触

`probe-contacts` 从已核验图层 PNG 的 alpha 计算接触区域，复用现有 RLE 接触算法，
不修改旧算法、人工关节草稿或生产状态。它是 R2 接触候选的前置诊断入口。

```powershell
$env:PYTHONPATH = (Resolve-Path ./src).Path
python -m autospine_workbench.benchmark probe-contacts --manifest docs/benchmark/manifest-frozen-v1.json --evidence docs/benchmark/development-audit-2026-09.json --workspace .. --character crino.psd --html ../tmp/benchmark-contacts/crino-v1.html --output ../tmp/benchmark-contacts/crino-v1.json
```

首版 profile `raw-layer-contact-probe-v1` 固定以下原始名称配对假设：

| 接触关系假设 | 参考图层原名 | 子图层原名 |
| --- | --- | --- |
| torso_arm | topwear | handwear（包括 -l / -r） |
| pelvis_leg | bottomwear | legwear |
| leg_foot | legwear | footwear |

衣物标签并不证明解剖语义。`topwear` 可能包含袖子，`bottomwear` 可能是裙子，
`handwear` 也可能与手臂混在一起。原名左右后缀不能直接确定角色自身左右。
因此报告始终保留语义未复核、侧别未复核和关节分配阻塞原因；`joint_id` 固定为空。
没有绕过腿图层建立骨盆到鞋的捷径，也没有用 bbox 中心补点。

图层按审计 bbox 偏移到 PSD 画布。前景为 alpha > 8，最大间隙为8像素；
显示显著重叠连通区或有界最近间隙，包含面积、重叠比例、接触 bbox、代表点、
端点与几何 QA。代表点只是该接触区域的几何代表，不等于 shoulder/hip/ankle。
空图层、越界、缺少配对层和无可用接触均明确报告；资源超限拒绝，不静默截断。

输出绑定原有语义候选。`read_contact_probe(..., workspace=...)` 重验原始素材、
audit 与全部图层字节并重算接触，拒绝改名、改图或重新哈希的伪造统计。
只允许冻结的 development 样本，不能通过此入口打开 holdout。新结果使用新文件名。

下一步需要确认身体/衣物接触角色、检测大面积遮盖和多接触歧义，再结合姿态证据
确定左右及关节位置。此诊断本身不证明定位改进、自动采用覆盖率或 Runtime 通过。

## 筛选深重叠和多区域歧义

`screen-contacts` 保留原始 probe，并新增独立的 `clothing-contact-screen-v1` 报告。
它重新核验相同素材，输出筛选摘要及完整原始接触图；不删除被排除的几何证据。

```powershell
python -m autospine_workbench.benchmark screen-contacts --manifest docs/benchmark/manifest-frozen-v1.json --evidence docs/benchmark/development-audit-2026-09.json --workspace .. --character crino.psd --html ../tmp/benchmark-contacts/crino-screen-v1.html --output ../tmp/benchmark-contacts/crino-screen-v1.json
```

全部配对角色仍为 `unreviewed_clothing_proxy`，没有自动把裙子标成骨盆。
同一配对存在多个接触区、同一关系存在多个图层配对或出现间隙，均进入复核。
不按面积取最大、不平均多个区域、不从画布X推测左右。

仅 `pelvis_leg` 衣物假设使用已有髋腿几何阈值的固定副本：

| 指标 | 需复核（含边界） | 深重叠排除（含边界） |
| --- | ---: | ---: |
| 接触占子图层 alpha 面积比例 | ≥ 0.10 | ≥ 0.25 |
| 接触 bbox 高 / 子图层 bbox 高 | ≥ 0.20 | ≥ 0.35 |

任一排除条件优先于复核条件。深重叠排除表示该接触不适合作为局部连接候选，
不表示素材应删除。其余单一局部接触可标 `local_contact_candidate`，仍不允许分配关节。
肩部和踝部阈值未校准，不套用髋部阈值，保持 `review_required`。

这些阈值未用本开发集重新调参，也尚未证明适用于衣物解剖定位；报告保存固定阈值、
源候选和probe身份，始终 `diagnostic_only: true`、`authority: none`、`joint_id: null`。
`read_contact_screen(..., workspace=...)` 重放所有源字节、原始接触与筛选，拒绝改阈值
或改状态后重新哈希的报告。后续需增加接触角色证据和姿态融合，才能解决左右与关节赋值。
