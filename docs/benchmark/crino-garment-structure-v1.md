# 琪露诺当前服装结构与动作恢复

2026-09-15。图层来自当前 PSD，不复用旧 PSD 的翼片清除决定。
工作台来源候选 `a33a2d031eac0327c77a60ae36678c24a5bbdb99dbce775a5f7c7732dfebe477`。

实际检查：layer-002 topwear 同时包含完整连衣裙、四组翼和挂饰；
layer-004 topwear-front 覆盖连衣裙主体；layer-000 wings 保留翼边缘。
因此不能将 topwear 按普通短上衣默认绑定，也不能重新要求用户擦除此前旧版本的区域。

现有工作台分区计划地址 `4e1ccba8969c5c73cc82c987949daad34861916b8afbab21f7add5bc0add254b`：

| 组件 | 非零 alpha 像素 | 距离最近骨骼（不是归属） |
| --- | ---: | --- |
| component-0000 连衣裙 | 197721 | thigh_l |
| component-0001 翼与挂饰 | 28717 | upperarm_r |
| component-0002 翼与挂饰 | 28669 | upperarm_l |
| component-0003 翼与挂饰 | 9477 | forearm_r |
| component-0004 翼与挂饰 | 9242 | forearm_l |

465 个残余像素单独保留。上述建议不能直接成为绑定：工作台现已将多组件衣层标为归属异常，
显示距离提示但不预选，明确选择后才可保存。实际部署 API 已返回 `garment_component_ownership_required`。
完整本地计划在 `E:/proj/unusual/localset/tmp/crino-garment-plan/guarded-plan.json`。

下一步需要把连衣裙的固定上身、腰部与裙摆结构接入通用候选，翼片及挂饰独立处理；
保持当前绘制顺序与覆盖关系，不能用统一腿骨或手臂骨掩盖混合语义。

## 新来源 walk

第一次恢复尝试 `job-ed700f2baff14ee0af70824620705ce0` 因动作源位于最终残余排除之后，
在合并前以 `character_motion_source_changed` 失败，没有运行成功的 Runtime 证据。
该失败记录保留。现在注册及选项入口提前拒绝这一阶段错误，不放宽重放校验。

正确动作合并源是排除前的 `c4a464481e6fc01daa9ac8f21fd9484ce3a9593d7188a6ed7d11486ac61ce58b`。
重建 walk 候选 `e1898111ce49b14525f1c4efdfbc874cfe934eb96bd00e5d689be6a88031e07c`，
新选择 `9ccde332123d1929cc1c052dd34853a8714521290a04ae293a009764b35e4e1a`。
固定 MotionIR、513 样本及原修正参数保留，未按角色调参。

相关 Python 11 项、Web 595 项通过。完整角色与动作视觉验收仍未完成。

新任务 `job-9d034bee08c54af385bbdf385d59a6d4` 完成：
输出 `f368ff50e902753b87fe4f939b7f1b3d1e0ad34b653876817a1dbb525385e9d5`，
官方 Runtime 1,028 帧，几何失败 0；idle、limb-flex-15、wave-left、walk 已恢复。
