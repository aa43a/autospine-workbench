# 批量检查当前项目的动画候选

项目完成关节复核后，可以按项目名称批量构建 15°、30° 两组屈伸候选，生成跨角色异常表。
此命令仅提交动画构建，不修改关节、绑定或采用决定；图层仍可为 pending。

启动主工作台服务后，在仓库目录执行：

```powershell
$env:PYTHONPATH = (Resolve-Path ./src).Path
python -m autospine_workbench.automation.animated_cohort_cli --base-url http://127.0.0.1:8918 --projects lumia huiye uuz yaomeng --output ../tmp/visible-cohort-v1
```

命令自动解析每个项目的 current 身份，顺序提交及查询任务，复用已有编译缓存。
每例最多等待 600 秒，超时请求取消；单个构建失败记入报告。服务连接或项目概览读取失败需修复后重跑。
完成时再次核对作者和动画来源身份；构建期间编辑过的结果被标记过期，不以旧结果宣称当前可用。
最多支持 20 个显式项目，不自动扫描或改变 benchmark 分组。

输出在以报告 SHA 命名的目录内，包括 `report.json` 和 `index.html`。
`animated_cohort_report.read_report()` 校验报告汇总、采用边界和内容地址。
报告保存 project、clip、run、job、bundle 和 source 身份；后续编辑不会修改此历史报告。
异常频次按角色／图层／reason code 去重，不因两个片段重复计算。

## 2026-09-09 可见测试集结果

四个项目均已由操作者完成 17/17 辅助关节复核；共 8/8 候选可编译，没有 Mesh 因本轮几何检查失败而退回刚性。

| 项目 | 活动 Mesh 附件 | 刚性上下文 | 总附件 |
| --- | ---: | ---: | ---: |
| lumia | 6 | 20 | 26 |
| huiye | 4 | 19 | 23 |
| uuz | 6 | 21 | 27 |
| yaomeng | 6 | 22 | 28 |

Mesh 数包括单骨脚部分区，不代表每个附件都是多骨柔性 Mesh；辉夜仍有大量裙装与长发保持静态上下文。
去重后的主异常是 75 个角色／图层绑定待选、8 个 Mesh 复核、7 个分区归属、7 个 residual 归属，以及每角色的接缝和视觉检查。
这些是待处理量，不是已确认的 75 个错误。

另行使用官方 `spine-webgl 4.3.13` 对四个 4.3.26 导出包执行 **30° × 61 帧，共 244 帧**验证，技术检查均通过，无页面错误。
最大运动坐标偏差约 0.00011673 px；身份与数值摘要见[实测记录](benchmark/visible-cohort-runtime-2026-09-09.json)。
15° 候选本轮没有独立 Runtime 复测。批量报告的 `runtime_status=not_evaluated` 保持原值，独立 Runtime 报告不被混入编译通过状态。

已查看四角色 bend 图片，并提供 setup／bend 对照页。裙装保持静态、手臂进入裙装遮挡等仍需视觉判定；固定帧数值通过不能证明宽袖形变、接缝和完整动作都合格。
没有独立 GT、没有补造此前人工耗时，也不声称自动采用精度达标。

## 下一主线

优先把 75 个绑定待选按 rigid／mesh／partition／secondary-motion 分类，提供可追溯的绑定建议和批量异常复核。
先缩减确定性刚性部件的重复操作，再处理宽袖、裙装和 residual；不继续只围绕某个角色的单点数值微调。
三个人工隔离的 holdout 保持未参与调参。R2-C 全十角色自动采用与 R3 完整 Mesh／接缝验收仍未完成。
