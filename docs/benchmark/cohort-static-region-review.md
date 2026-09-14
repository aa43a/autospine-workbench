# 未绑定静态区域集中复核

对 `first-ten-workflow-v6.json` 中尚未完成的已有候选运行：

```powershell
$env:PYTHONPATH='src'
python tools/review-cohort-static-regions.py --snapshot docs/benchmark/first-ten-workflow-v6.json --output ../tmp/character-cohort-residual-review
```

每个输入包通过 AnimatedStore 的内容地址及逐文件摘要验证。输出保留快照摘要、项目、job、候选地址、区域、源纹理摘要及 alpha 统计。候选更新后必须重新生成；本报告不是在线 current 状态。

本次共 18 处静态区域：12 处仅含 alpha 1–7 的像素，1 处为空纹理，5 处含 alpha ≥8 的内容。空纹理为芙兰 `layer-023`，并非低透明度残余。页面复用现有原图裁切与 alpha 增强诊断，不修改像素、绑定或采用状态。

低透明度不能代替排除授权。含可见内容的铃仙 `layer-018`、幽幽子 `layer-004-unbound-residual`、芙兰 `layer-000`、爱丽丝 `layer-008` 与 `layer-022` 保留归属复核。统计包含完整静态参考层，不应将全部 18 处都称为边缘残余。

当前鞋层中，爱丽丝、露米娅、芙兰和幽幽子仍有静态残余，因此不能以有效鞋区的单骨权重证明整个源层已完成。集中复核后，应按明确区域记录可撤销排除或绑定，再重建候选与验证。

验证：真实候选生成报告成功；静态区域及代码质量测试共 6 项通过。未新增任何人工确认、视觉验收或发布权。
