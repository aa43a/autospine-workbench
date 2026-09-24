# M4 主线核对：姿态附件实验之后

2026-09-24；代码基线 `27b6769`。本次只读核对实际工作台和冻结候选，
未重建角色、未生成模型动作、未重新捕获动画、未更改任何人工判断。

## 当前可证明的结果

- 8918 工作台返回 165 个动作任务：154 succeeded、11 failed，无 pending/running。
  这是任务状态，不代表动作质量通过。
- 固定 v3 三角色×八动作的 8 个来源和 24 个候选均通过精确身份核对，
  当前候选均可读取，未发现实验结果覆盖冻结候选。
- 24 个已有 Runtime 证据合计 11,334 帧；此次只是读取原证据。
- 当前几何通过 11/24，完整技术通过 0/24，24 个候选均 needs_changes。
- 分阶段待处理：投影 18、几何 13、接触 15、遮挡 24、Runtime 0；
  其中 8 个候选存在未完成的深度检查。计数不能当作视觉错误率。
- 本轮没有读取新的人工阶段判断快照，不能把 report 函数在缺少该输入时的
  visual_accepted=0 解读为撤销历史三项 Breathing 接受。

新状态快照：`localset/tmp/m4-motion-center/cohort-audit-after-variant-v1.json`。
读取用 `m4_motion_cohort_refresh.py`，校验来源 SHA、候选 artifact、诊断身份，
在每个候选读取前后再次确认当前身份；历史 state 文件未改动。

## 任务生命周期回归

以下测试共 26 项通过：`test_motion_generation`、
`test_motion_generation_lifecycle`、`test_motion_kimodo_intake`、
`test_motion_bundle_kimodo`、`test_motion_kimodo_commands`。
生命周期测试实际创建并停止 Windows 合成工作进程及子进程，检查取消、
关闭、重试及历史请求不变；不是重新运行 Kimodo 模型或新的模型质量证据。
已有真实生成与导出证据分别见 `m4-kimodo-generation-v1.json`、
`m4-generation-replay-delivery-v1.json` 和 `m4-kimodo-foot-timeline-v2.md`。

## 未完成项与下一决策

近期新增的内部细分、姿态附件替换、活动网格采样与切换捕获均为实验能力，
没有改变 Reach/Squat 的质量状态。实际新膝形仍缺失，不能把通用验证工具
或同表面回归算作 M4.2 完成。

Squat 的正面透视与侧向夸张表现选择已询问用户，尚未收到答复；等待不构成
接受。Reach 肩部材料连接与遮挡仍为独立未完成项，不能因 Squat 待答复
而从目标中删除。下一步不再为通过率重跑同一批候选或重复已失败参数搜索，
应处理这些表达缺项，或把必要的姿态素材需求交付到现有异常修改入口。

M4 未完成；本次没有请求发布、自动撤销既有接受或将实验设为默认。
