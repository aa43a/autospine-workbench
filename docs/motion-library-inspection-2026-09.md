# 本地动作库检查（2026-09-07）

用户提供的 C1455-mo 动作库共11632文件，其中5503 FBX、2934 iMotion、900 anim、
103 bip；未发现 BVH 或 blend。只读取源文件，没有执行库中的脚本或修改素材。

用本机 Blender 5.2.1 LTS 实际导入 `01/breathing_idle.fbx`：FBX7400、1 armature、
53骨、根 Hips、1 Action，帧范围1–299。源 SHA256 为
`67bf8b91cb77fec8873bb059cddcb96198c9ca348a16cfa6eb60171dabbd5370`，导入前后相同。
场景30 FPS是检查环境设置，不证明文件原始采样率。没有角色 Mesh 或材质。

在工作区外部产物 `../tmp/motion-library-inspection/` 保存 inventory.json、
breathing-idle-blender.json、检查脚本、三个采样截图及调试 blend。
蓝线为导入的 bone head→tail，绿线为父子 head 连线，橙点为 joint head。
部分 tail 不与子骨 head 重合，不能直接按显示骨长推断人体骨段。
调试 blend 只含1/150/299三帧离散姿态，不是完整动画重建或 Spine Runtime golden。

后续可做独立 FBX→MotionIR Adapter：先明确源采样率、坐标/单位、root motion、
Mixamo命名映射和骨架拓扑，再验证逐帧确定性。bip/iMotion等不能视为已支持格式。
这次检查不构成 Blender 2.5D输出适配，不挤占 R2/P3 主线；素材不进入 Git或分发包。
