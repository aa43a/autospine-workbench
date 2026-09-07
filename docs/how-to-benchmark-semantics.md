# 开发集图层语义复核

此入口直接查看 PSD 坐标中的图层，不需要把尚未确认的 PNG↔PSD 映射当作批准。
页面显示合成图、逐层 PNG、bbox、名称建议、空层/可见性与待标注控件。
它不会修改 PSD、历史 Rig、主工作台 override 或正式真值。

```powershell
$env:PYTHONPATH = (Resolve-Path ./src).Path
python -m autospine_workbench.benchmark semantic-review --manifest docs/benchmark/manifest-frozen-v1.json --evidence docs/benchmark/development-audit-2026-09.json --workspace .. --character crino.psd --html ../tmp/benchmark-semantics/crino-review-v1.html --output ../tmp/benchmark-semantics/crino-candidates-v1.json --draft-output ../tmp/benchmark-semantics/crino-pending-v1.json
```

同样可选择 `alice.psd`、`lingxian.psd`。当前入口只开放冻结开发集；holdout 不读取。
CLI 核验所选原 PNG、PSD、合成图、audit 原始字节及每张图层 PNG 的 SHA、大小和尺寸，
再交叉核对审计中的索引、名称、bbox、alpha 非零数量、empty 和 visible 字段。
这是身份与记录一致性检查，不是重新运行分层算法或视觉质量认证。

`exact-layer-name-v1` 只将明确名称映射到19项语义词汇。`handwear`、`legwear`、
`bottomwear`、未分段 arm/leg 等保留歧义。眼、眉、睫毛、耳朵等未被当前词汇覆盖的
局部层不会一律归为面部；待后续 Attachment 词汇扩展。名称中的 l/r 只是原始标记，
没有确认镜像/左右约定前，canonical side 始终 unknown。bbox 和 alpha 审计标记供复核，
当前算法不使用位置、姿态或接触几何推断语义，confidence 保持 null。

每层标注初始为语义空值、左右未知、是否纳入未决定，算法建议单独显示。
操作者可以选择语义、角色自身左右侧、纳入/排除并填写备注，再下载草稿。
草稿可在同一页面恢复；重复/缺失图层、陌生词汇、错误候选地址或假批准字段均拒绝。

用下载的 `semantic-draft.json` 重建页面并封存草稿：

```powershell
python -m autospine_workbench.benchmark semantic-review --manifest docs/benchmark/manifest-frozen-v1.json --evidence docs/benchmark/development-audit-2026-09.json --workspace .. --character crino.psd --draft semantic-draft.json --html ../tmp/benchmark-semantics/crino-edited.html --draft-output ../tmp/benchmark-semantics/crino-edited.json
```

不同内容使用新输出文件名，历史文件不会被覆盖。候选、审计快照、证据清单和草稿
分别按内容寻址保存。`read_semantic_candidate` 重读完整闭包并重新计算建议，防止
改过建议后重新计算哈希冒充原算法输出。标注草稿不参与算法候选身份。

此入口的纳入/排除只属于待复核标注，不会删除图层或自动批准其语义。正式语义复核见下文，
[关节点录入](how-to-benchmark-joints.md)使用独立草稿；左右/pose/contact融合及 policy_auto 待实现。PNG 坐标关节进入 PSD
时仍需单独验证对应映射；当前 PSD 局部语义候选没有绕过这条边界。

## 显式采用语义草稿

页面提供接受/拒绝的复核请求，默认不选择、不勾选。接受要求所有层明确纳入或排除；
纳入层有语义，成对肢体有明确侧别；空层不能纳入，每个排除项需要备注说明。
操作者须填写复核人、原因并检查图层身份、语义、左右侧。修改草稿后先下载并用
`--draft` 重建页面，再复核新版本，防止请求引用旧草稿。

实际检查完成后下载请求，使用对应候选和草稿显式记录：

```powershell
python -m autospine_workbench.benchmark record-semantic-review --manifest docs/benchmark/manifest-frozen-v1.json --evidence docs/benchmark/development-audit-2026-09.json --workspace .. --character crino.psd --candidate ../tmp/benchmark-semantics/crino-candidates-v1.json --draft ../tmp/benchmark-semantics/crino-edited.json --request semantic-review-request.json --confirm-human-review --output ../tmp/benchmark-semantics/crino-decision.json
```

请求下载本身不是已记录决定。CLI 再次核验实际输入文件，保存候选、草稿、请求及决定，
`read_semantic_decision` 沿完整闭包重算。决定仅作用于 Benchmark 语义，仍不产生
Rig、主工作台 override 或发布权。复核人是本地填写的声明，不是身份认证。
没有隐式 latest 或撤销语义；后续消费必须明确指定一份精确决定。
