# 残余归属复核与规则试算

`review-partition-residuals` 从精确分区回执生成对照页和整份草稿。
页面右侧始终是规则试算，不随左下选择变成已采用结果；所有新草稿默认 pending。

```powershell
python -m autospine_workbench.benchmark review-partition-residuals `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --partitions ../tmp/r2b-partitions/alice-v1.json `
  --html ../tmp/r2b-residual-review/alice-v1.html `
  --draft-output ../tmp/r2b-residual-review/alice-draft-v1.json `
  --output ../tmp/r2b-residual-review/alice-v1.json
```

每层可选择待复核、保留残余、4px 邻近规则。后两项需要复核说明。
选择后保存整份草稿，可恢复、撤销。重新运行时附加 `--draft <下载文件>` 并指定新的输出文件名，
即可验证来源并封存草稿及其试算报告。不同分区来源、未知策略和额外字段都明确失败。

## 规则边界

种子是原 ownership 已属于左/右且 alpha≥8 的像素。
四连通最短距离可跨越透明背景，最多 4 步；只修改原来属于残余且 alpha 为 1–7 的像素。
等距、远处和高alpha残余不分配，透明 RGB 保持原样。规则不能改变已有左右分区。
每次试算都重建全部 RGBA 并检查逐字节一致。该距离规则仍需复核，不是几何正确率保证。

对照页同时显示残余像素数量及其占源图层 alpha 总量的比例。
例如铃仙腿部 30,893 个残余像素占 alpha 总量约 0.222%，4px试算后为 30,802 个、约 0.220%。
六层试算合计移动 673 个低alpha像素；六项草稿仍全部 pending。

## 身份和后续工作

`residual-draft/v1` 绑定精确 partition SHA；`residual-review/v1` 同时引用分区与草稿 SHA。
`read_review` 重放原始来源、旧分区、规则与草稿后重新计算，不能只修改统计字段冒充结果。
草稿不是 Binding Decision 或正式分区采用；本切片不改写旧 PNG/ZIP、Mesh 或绑定。
试算输出用于对照，不作为已采用的权重输入。

17项相关测试通过，覆盖距离上限、平局、高alpha残余、字节重建、默认pending、来源校验、
Schema和浏览器草稿验证。三个真实来源均重放，铃仙页面截图检查通过；未运行全量或官方Runtime。
见[真实试算记录](benchmark/residual-review-2026-09-08.json)。

下一步将明确选择的规则封存为独立新分区版本，并接入多区域权重实验。
若保留残余，必须继续携带独立残余附件；不得丢弃后宣称完整角色重建。
