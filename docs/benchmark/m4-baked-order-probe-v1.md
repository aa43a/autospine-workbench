# Reach：烘焙躯干平面与保序细化验证

2026-09-25。结论：仅修正参照平面不足以解决当前 Alice Reach 遮挡；停止将此路线当作独立修复方案，不扩大预算、不删除失败约束、不自动改为手臂在前。

## 精确输入与结果

- 在线任务：`motion-c54fd4c586ee439d8c2c38e8037f4c6b`。
- 候选：`cb2f7dbccb796996108be3508293f2f5f0fee98b623ecaa4b4930b4ee7219fab`。
- 原始与试验后均为 119 处排序失败：37 处 `visible_unmapped_order_conflict`，82 处 `visible_depth_straddle`。
- 82 条歧义记录，消除 0 条。163 次源帧/中点检查中，151 次得到 `uniform_front_proxy`，12 次仍需分区或更多深度证据。前者不能支持现有相反的保序决定；不能把它计为已解决。
- 使用 3,583,978 像素采样；保持原预算和全部排序约束。
- 没有产生候选 skeleton，没有执行新的 Runtime 捕获，没有写入采用或视觉接受记录。

## 实现和复现

`depth_straddle_refine.refine` 支持显式参照平面，并在逐对重建 Checker 时保留同一 provider；只有躯干模型模式接受该参数。默认调用不变。

离线工具 `tools/m4_baked_depth_order_probe.py` 校验来源，以 `BakedWarpPlane` 对齐实际烘焙 deform 的虚拟标记时间表，随后运行原排序门禁。它是诊断入口，尚未接入生产构建策略。

```powershell
$env:PYTHONPATH='src;tests;tools'
python tools/m4_baked_depth_order_probe.py motion-c54fd4c586ee439d8c2c38e8037f4c6b tmp/m4-baked-order/alice-v1
```

输出目录必须不存在。完整证据保存在上述目录的 `report.json`；紧凑、带完整报告摘要的证据见同目录文档下的 `m4-baked-order-probe-v1.json`。深度仍是躯干平面代理，不是观测到的衣料表面；用户确认的披肩覆盖袖子、可相对滑动关系保持。

13 项回归通过，覆盖保序、源帧/中点、显式平面的逐对重建及烘焙坐标合同。下一步不能直接重排整个手臂或将本结果称为质量通过，需要处理局部衣料遮挡表示。

## 独立启动修复

`start-local-workbench.ps1` 的 Pose 前置检查改用标准输入传递 Python，避免 Windows PowerShell 将字典键及字符串引号剥离。Windows PowerShell 与当前 PowerShell 的 `-CheckOnly` 均返回 ready。此检查不启动或停止服务；服务重启仍未执行，在线进度新模块仍待部署验证。
