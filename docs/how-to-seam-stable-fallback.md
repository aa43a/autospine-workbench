# 按附件整段回退候选

本切片显式选择 Alice `layer-002-l` 的完整附件动画轨道恢复到连续锚点版本，
其余轨道保留增量结果。没有逐帧开关，也没有重新求权重。
这是一份新的可复核候选，不改变已采用结果或 source 工件。

```powershell
python -m autospine_workbench.benchmark.seam_stable_fallback_cli `
  --before ../tmp/r2b-continuous-anchor/alice-v1.json `
  --after ../tmp/r2b-seam-increment/alice-v1.json `
  --before-dir ../tmp/r2b-continuous-anchor/alice `
  --after-dir ../tmp/r2b-seam-increment/alice `
  --follower layer-002-l --output-dir ../tmp/r2b-stable-fallback/alice
```

输出独立 `seam-stable-fallback/v1` 报告、Spine JSON/Atlas/图片和 preview.zip。
`--follower` 是明确的候选选择，不是人类批准；工具未实现自动采用策略。
reference 与 candidate 必须具有相同骨骼、slot、skin 和骨骼动画，缺失或重复选择失败。
原语义报告通过 source_anchor_sha256 关联，文件身份逐项核验。
`read_fallback` 重算本切片并比对地址；不替代上游完整编译链的 reader。
Schema 检查 envelope，嵌套 QA 语义由精确重算与数值检查验证。

## 2026-09-08 结果

- Alice 四区域几何采样通过，左右原对应增距 1.968960／1.727884px，均低于2px。
- 原边界样本与对应对完全保留；相对 reference，左右新增空白帧均为0。
- 左侧共同走廊峰值4→4，右侧3→1。原有空白不因此消失。
- 官方4.3.13 Runtime加载4.3.26目标，原／回退各121帧对照通过。
- 七个目标像素单元在1／4倍密度、共享／独立纹理及四种隔离／合成模式下，
  before／after RGBA全部一致；共224次捕获、112组配对比较。
- 45项针对性测试、精确reader、文件SHA和确定性ZIP验证通过；未运行全量Python/Web测试。

该结果消除了上一版 Alice 左侧增量带来的已确认透明度退化，并保留右侧改善。
仍为 needs_review / authority:none；Runtime范围仅为Alice已有候选区域，不覆盖完整角色。

下一步把几何、边界增距和合成退化整合成可解释的逐关系候选准入报告，
再对琪露诺执行同类Runtime验证。保留原有空白、颜色重叠及未覆盖区域作为独立门禁。
