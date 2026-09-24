# 父链修正后的脚部补偿：鞋改善，腿部回归，未采用

2026-09-24。对红美铃 Squat 姿态附件实验检查发现：原脚骨已有 rotate/scale/shear
通道，后续腿部投影和端点 IK 改变了其父链，却继续使用原脚部局部补偿。
相对父候选同帧世界变换，右脚出现约 54° 朝向差、非均匀尺度比最高约 1.898。
原脚踝坐标相对父候选几乎不变，不能代表鞋部形状与位置保持。

新增 `foot_frame_preservation.preserve`，对确切 reference 世界线性变换重新解
脚骨局部旋转/缩放/剪切，保留 candidate 脚踝位置、骨骼绑定、纹理和 deform。
通过四分点递增检查插值，容差 1e-3，最多 4097 键和八次细化；不放宽网格门槛。
`group_target_contact.constrain` 仅显式 `preserve_foot_frames=True` 时调用，默认关闭。
不能将本实验当作默认大幅 Squat 修复。

## 真实输入与结果

输入 document `1ded2804907575e54987322ec2cfc32fbc2189ffe1375d2ce579777c2c33c0b5`；
参考 artifact `051cb629d2a3f1b963c03ebbef3d585d0c3e1c551705d9e57a7b83f423c2d918`；
输出 document `5d71e1b2d3018cbb7c7049c7de91ae7a00449ec9f17291b9aa06f177d42fe149`。

349 键、1393 个变换检查时刻，最大相对系数误差 0.00099321，脚踝位置改变 0。
独立 697 时刻整角色几何检查；官方 Core 4.3.13 对目标 Spine 4.3.26 正逆向
1394 次采样核对通过，最大世界顶点误差 0.00017348 px。不是 GPU 视觉验收。

同采样对照：

| 附件 | 失败帧 前→后 | 翻转三角形采样 前→后 |
| --- | --- | --- |
| layer-003 原腿 | 227→269 | 0→125 |
| layer-004 腿 | 587→623 | 1397→1141 |
| layer-008 鞋 | 5→0 | 0→0 |
| layer-003 姿态腿 | 243→243 | 471→566 |

之前六个材料探针的相同 163 时刻，左鞋最大位移降至约 4.93–4.95 px，
右鞋降至约 4.24–4.33 px。但腿部存在新增翻转，因此明确拒绝整体采用。
探针区间仍非人工确认驻足，降低位移不代表地面接触通过。

证据：`localset/tmp/m4-motion-center/foot-frame-preservation-v1/` 中 candidate、report、
geometry、active-reference、official-core、comparison JSON；均为独立实验。
复现入口 `tools/m4_foot_frame_probe.py`。

后续应在相同失败姿态处理 calf/foot 混合权重交界的表示问题；单独恢复脚部
世界变换会改变共享权重顶点，不能以鞋部改善掩盖腿部回归。原候选与人工
接受记录不变。Reach 肩部及 Squat 膝形仍未解决，M4 未完成。
