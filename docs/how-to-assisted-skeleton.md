# 用辅助复核坐标生成候选骨架

本入口读取已经由 `joint-review --draft` 封存的模型辅助标注，保留用户修正的全部17点，
生成20骨候选与角色叠图。适用于当前正面站立角色；中央纵向顺序是该profile的约束。

在仓库目录运行（Python环境需能导入本项目）：

```powershell
python -m autospine_workbench.benchmark build-assisted-skeleton `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --draft ../tmp/r2b-reviewed/crino-2026-09-08.json `
  --html ../tmp/r2b-skeleton/crino-v2.html `
  --output ../tmp/r2b-skeleton/crino-v2.json
```

Alice、铃仙对应文件名为 `alice`、`lingxian`。尚未封存或修改后的草稿应先通过
原有 `joint-review --draft` 接口录入。页面和JSON采用不可变导出，修改后请用新的输出名称。
同一输入重跑会得到同一内容地址，无需填写SHA。

绿色骨段直接使用辅助复核点，蓝色为躯干中点推导，橙色为头/手/足末端延伸。
root、pelvis、chest、neck、head不再由肩或髋的中点替换。
头末端延伸为躯干长度的15%，手/足为5%；末端方向沿相邻骨段，不表示完整解剖方向。

17点必须全部在用户复核清单内且具有observed坐标；否则返回 `blocked`、空骨架与原因码，CLI退出码2。
中央纵序、至少1px骨长和所有端点的画布边界必须通过。有效候选退出码0，
状态仍为 `candidate_requires_review`。未支持姿态不会通过夹紧坐标静默修复。

内容寻址 reader 重新读取辅助envelope、语义候选、原Pose、旧基线、audit和源PNG，
再重建并比对骨架。源文件变化、地址不符或骨架字段篡改会拒绝读取。
原Pose及旧JointOptimization/skeleton合同不改变，辅助数据仍不是独立GT或生产决定。

2026-09-08实际验证：三个角色均20骨、17个标注坐标逐一保留，
局部变换重建最大坐标差约1.14e-13 px，重复构建地址一致。
[验证清单](benchmark/assisted-skeletons-2026-09-08.json)记录完整地址及逐角色结果。
Chrome实际渲染检查了琪露诺页面。相关单测和CLI测试共19项通过，含Schema、
FK、未复核阻塞、不可观测点、退化骨段、越界、源篡改及文件长度门禁。
本切片未运行全量Python/Web测试或官方Runtime；未修改Spine导出器。

下一切片为图层绑定候选、复核冲突和region setup重建。本次没有Mesh、动画或正式导出，
也不据此宣布R2自动region rig里程碑完成。
