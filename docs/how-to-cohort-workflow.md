# 首批十角色实际验收进度

2026-09-15 最新读取：首批十角色完整验收 5/10（铃仙、辉夜、咲夜、八云蓝、露米娅），9 名角色有已测候选，必需动作 27/30。
对应 [十角色结果](benchmark/first-ten-workflow-v11.json)。固定三角色此前完整验收 3/3、必需动作 9/9，见 [三角色结果](benchmark/fixed-three-completion-v1.json)。下方时间点记录保留历史统计。

来源核对通过只表示找到了对应 PSD，不表示整角色已完成。现在可以在已核验来源清单上
读取每个项目的当前候选、真实 Runtime 报告和人工复核，并复用固定三角色的同一套验收条件。

```powershell
$env:PYTHONPATH='src'
python tools/assess-cohort-intake.py --verify-workspace .. `
  --source-versions docs/benchmark/first-ten-source-versions-v2.json `
  --output ../tmp/character-first-ten-workflow-intake
python tools/assess-cohort-workflow.py `
  --intake ../tmp/character-first-ten-workflow-intake `
  --output ../tmp/character-first-ten-workflow
```

打开输出目录的 `index.html` 查看进度与项目入口。`report.json` 保存逐角色的缺失动作、
未完成绑定、自动证据过期和视觉复核状态；`observations.json` 保存对应读取证据。
页面按角色并排显示图层绑定、几何、三个必需动作、人工视觉及整体结果。展开待处理数量可查看图层清单，
候选入口打开本次读取的确切任务。页面是读取快照，项目修改后须重新运行上述评估，不会自动刷新。
来源快照摘要不匹配、目录项目来源发生变化、候选和复核身份不同会拒绝统计。
同一个项目不能重复作为两名角色计数。

分母始终为十角色、三十组必需动作。版本尚未选择、尚未构建的角色仍留在分母。
Runtime 失败率只针对实际测量的角色；人工总耗时和错误自动采用率缺乏证据时仍为 null。
已被开发和人工调整的角色不计作独立 holdout。

2026-09-13 首次实际读取：

- 固定三角色：9/9 必需动作技术检查通过，0/3 完整视觉验收已保存。
- 首批十角色：咲夜完整候选已验收，当前 1/10；已测两名角色，6/30 必需动作技术检查通过。
- 妖梦仍需选择 PSD 版本；其余角色按实际准备、绑定及视觉状态逐项推进。

这些是读取时点的当前候选状态，不是全部历史局部测试的累计通过率，也不是总体自动化成功率。

后续幽幽子的确切归属、挥手策略对照及整角色验证见 [幽幽子推进记录](benchmark/uuz-whole-character-progress.md)。单角色新增动作不自动提高整角色完成数。

爱丽丝、铃仙、露米娅的当前三动作候选和仍待复核范围见 [普通路线三角色推进](benchmark/ordinary-cohort-progress.md)。

2026-09-13 后续读取：当前已测 7 名角色，18/30 必需动作技术检查通过，完整验收仍为 1/10。芙兰四种袖装测试不计入三种必需动作；见 [芙兰候选记录](benchmark/flandre-binding-progress.md) 与 [本轮统计](benchmark/first-ten-workflow-v2.json)。人工耗时和错误自动采用率仍未测量。
