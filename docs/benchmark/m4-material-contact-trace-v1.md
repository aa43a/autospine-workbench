# 活动附件材料轨迹：接触检查的前置能力

2026-09-24。`material_contact_trace.trace` 接收确切 document hash、动画、闭区间
采样、材料 UV、纹理路径与字节 hash。它追踪活动附件中该材料位置相对区间
起点的位移；不同顶点数通过 UV 三角形重心映射，不按顶点编号对应。

隐藏附件、覆盖缺失、多个不同世界位置对应同一 UV、换贴图缺少对应等情况
保留未解析。起点缺失不会从后续可见帧重新起算。超出动画长度直接拒绝。
有已测超限为 false，存在未解析且无已测超限为 null；没有自动采用权限。

该接口**不识别鞋底、不推断地面、不自动生成驻足标签，也未接入默认通过门禁**。
目前为 CPU 材料轨迹，GPU/透明混合/区间内未采样时刻均未验证。

## 真实诊断

对冻结姿态附件包
`818e98fa29dd431d41cdf38e67bc6f1f8c7526e73257dfce360a3966d1ac96eb`，
`tools/m4_material_contact_probe.py` 从纯 foot 权重的两张鞋附件中，在 setup
不透明可见下缘 1 px 范围内分别选择横向两端和中间像素中心，共六点。
这些是自动诊断探针，没有冒充已确认鞋底。

163 个时刻，六点均可解析；layer-007 三点最大位移约 16.84–17.03 px，
layer-008 约 134.17–153.57 px。显式诊断阈值为 2 px，故诊断 passed=false；
这不是新增生产阈值，也不能据此判滑脚——区间是完整捕获跨度，没有使用
源动作确认的驻足标签，正常抬脚/转脚同样会产生这些位移。

报告：`localset/tmp/m4-motion-center/pose-attachment-variant-v1/material-contact-probe.json`。
没有新 Runtime 捕获或历史候选更改。测试包括同材质拓扑切换、骨骼不动而
deform 移动、起点隐藏、纹理身份错误、换图缺少对应及动画越界。

下一步需将请求绑定到来源明确的驻足区间，再与实际 Runtime 顶点逐点核对。
不能将材料可追踪、脚踝代理通过或本诊断报告，单独写成鞋底接触通过。

## 来源核对与官方 Core 复算

Squat 原始 MotionIR `fb57014391df27c737995214f3ec89918b99192ceda0b4d1626d8cfbfc261061`
的 markers 为空。其 bundle 为
`ef7afe08aab29cb0b617aefd9c7d2162f96b2930dba70f8b37a61c2d88e5c2ab`。
父候选 `051cb629d2a3f1b963c03ebbef3d585d0c3e1c551705d9e57a7b83f423c2d918`
保存的驻足假设为 `bvh-declared-up-stationary-ankle-v2`，两腿半开区间
[0, 1866667) tick，1000000 tick/s；authority=none、selected=false。
其 limitation 明确不能区分低速悬空与真实支撑。因此没有把该假设改写为
人工驻足或真实鞋底接触，也未将捕获闭区间等同于完整来源区间。

新增 `tools/check-material-contact-core.mjs`：验证冻结包 inventory、原骨架字节
hash 与探针纹理身份，使用实际活动附件的 Runtime regionUVs、triangles 和
worldVertices 重新求材料点。独立正向/逆向采样共 1956 点次，最大误差
0.0001021815 px，结果通过。目标 Spine 4.3.26；实际官方 Core 4.3.13。
这不是新 GPU 捕获，也不代表接触接受。

证据位于同目录：`material-contact-probe-v2.json`、`material-contact-core-v1.json`。
Core 检查输入报告 SHA256 为
`5e6194c79f1fa802f389fa9471ef5c7b8f09c3efaa5ce7148adc43f67edfb5ad`。

## 位移归因

同区间左/右 foot 骨原点最大位移分别约 6.960/7.254 px；右鞋三个材料点
位移为 134.17–153.57 px。保持骨骼、时间与权重，仅去掉 deform 的反事实
结果与原材料点完全一致，最大差 0。
`material-contact-attribution-v1.json` 保存逐点数据。

因此该案例右鞋大位移并非局部 deform 引入；后续应检查 foot 继承的线性
变换（旋转、缩放及父链影响）。目前不能从这些数字断言只有旋转错误，
也不能据此自动锁死整只鞋或改变源动作。这一归因不解决既有膝部轮廓问题。
