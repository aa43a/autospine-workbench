# 烘焙 corrective 动画与纹理预览

`bake-elbow-preview` 从精确 Mesh 来源生成两秒测试循环：0° → +90° → 0° → −90° → 0°。
30 FPS 共 61 个关键帧，包含重复的结束状态；播放器跳过重复端点以保持两秒周期。

```powershell
python -m autospine_workbench.benchmark bake-elbow-preview `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --mesh ../tmp/r2b-mesh/alice-joint-plane-v2.json `
  --html ../tmp/r2b-mesh/alice-bake-v2.html `
  --output ../tmp/r2b-mesh/alice-bake-v1.json
```

`lingxian`、`crino` 同理。输出是 `elbow-bake/v1` 实验工件，不是 Spine 时间轴。
每个顶点的每个影响骨保存局部 corrective 偏移，按原 Mesh 的顶点和影响顺序解释；
无需改写已确认骨架或原三骨权重。JSON 使用既有 16MiB 实验 Mesh 存储，旧工件地址不变。
`benchmark.elbow_bake_cli.read_bake` 完整重放来源并重算所有关键帧及 QA。

## 插值与播放

角度与局部偏移均线性插值，QA 以 120Hz 检查两秒内 241 个采样点，包括帧间四分点。
检查面积比、翻转、边长、与完整约束求解的像素差、setup 和循环闭合。
沿用面积比 0.5–2、边长比不超过 2，并使用实验插值误差上限 0.5px。
不满足任一检查时保留关键帧供诊断，状态为 `blocked`；未选 Mesh 仍为 `not_evaluated`。

HTML 使用精确来源 PNG，WebGL 直接绘制三角形，避免 Canvas 裁剪抗锯齿产生伪接缝。
可播放、暂停、拖动帧号或显示网格；它按 30FPS 展示关键帧，120Hz 数值 QA 是独立检查。
只显示已选手臂，不将此局部预览宣称为完整角色动画；WebGL 也是工作台预览器，并非官方 Spine Runtime。

四臂实测全部通过本项采样 QA，最小面积比约 0.549，翻转 0，最大插值误差约 0.130px，首尾误差 0。
[验证记录](benchmark/elbow-bake-2026-09-08.json)保存独立地址和逐层数值。
43 项 Python 测试、1 项 JS 播放时序测试通过，三份真实工件完成 Schema、数值重算和 CAS 读回。
Chrome 核对纹理显示；未运行全量 Python/Web 或官方 Runtime。

## 后续范围

下一步接入完整角色的接触锚点与跨图层接缝检查，以及 Spine 4.3.26 deform 时间轴候选导出。
仍需验证关键帧的目标格式编码、官方 Runtime 采集与栅格对照。
本次没有正式视觉 golden、连续时间保证、独立肩腕/组合动作或跨图层 seam 通过声明。
