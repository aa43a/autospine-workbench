# R2-A：姿态到候选骨架的技术链

R2-A 验证可插拔姿态输入、接触匹配、受约束优化、canonical skeleton 的实现链，
不等待真实 GT。R2-B 是三个开发角色的定量验证，R2-C 是首批十角色达到自动 region rig
指标；它们仍需要真实检测、人工参照与生产策略。三者不能互相代替。

## 一次运行

```powershell
$env:PYTHONPATH = (Resolve-Path ./src).Path
python -m autospine_workbench.benchmark build-r2a --manifest docs/benchmark/manifest-frozen-v1.json --evidence docs/benchmark/development-audit-2026-09.json --workspace .. --character crino.psd --pose-observations path/to/pose.json --html ../tmp/r2a/crino-v1.html --output ../tmp/r2a/crino-v1.json
```

`pose.json` 使用已有 `autospine-pose-observations` v1/v2 合同，必须绑定所选角色的
character ID、PSD 合成 PNG 的 SHA 和完整画布。原 PNG 的检测不能直接冒充 PSD 坐标；
需通过已验证的坐标适配。原始模型观测与优化结果分别封存，不修改人工关节草稿。

双侧接触匹配要求 v2 的镜像状态明确且视角为正面或轻微3/4。已有 COCO17 Adapter 可
输出 v2；换模型不改后续匹配、优化和骨架合同。文件导入入口不执行模型或隐式下载。
不提供姿态输入时命令输出结构化阻塞、零骨骼、退出码2，不产生 bbox 替代观测。

`runners.pose.ModelRunner` 通过 `produce(PoseRunnerRequest) -> Path` 接入独立生产器。
请求包含原图路径、SHA、画布和项目身份，进入生产器前核验真实PNG字节与尺寸。
当前CLI已接 `CanonicalPoseFileImporter`，只导入已有标准观测，不冒充模型推断。
模型生产器可以在独立环境生成同一合同文件；现已增加 [DWPose ONNX Runner](how-to-real-pose.md)，
MMPose/MediaPipe具体Runner仍待接入，核心环境不增加这些依赖。

## 算法边界

1. 复用原始 alpha Contact Probe 和独立 Screen，排除深重叠。
2. 肩/髋/踝按可见且分数 ≥0.5 的双侧姿态锚点匹配不同接触区域。距离不得超过画布
   对角线8%，最优与次优总距离差至少为对角线1.5%。模糊、缺点、远距离均阻塞匹配。
3. 优化器要求12个肢体关节点完整、可见和非退化。接触拉动权重0.35，每点位移不超过
   对角线4%；有限全局回退步长保持8段肢体骨长比在0.75–1.25、画布内和最低骨长。
   这是确定性的有限可行解搜索，不宣称全局最优。无可用接触可保留 Pose-only 候选。
4. 生成20骨 canonical skeleton，保存 head/tail、世界角度、长度、父子 setup-local
   变换和来源。中央关节由髋/肩推导，头颈和手足末端仍是明确标记的比例 fallback。
   出界、骨长不足或不支持的姿态输出 blocked，不静默裁剪。

原始姿态、匹配、优化、骨架和R2-A报告都有精确地址。`read_r2a(..., workspace=...)`
重验源字节、姿态文件工件并重算全链，拒绝改坐标、阈值、来源或批准字段的伪造报告。
新模块位于 `asset/joints` 与 `runners/pose`；历史 RigIR、P9/P10 和 Spine Adapter 不改动。

## 技术验证与生产边界

`tests/test_benchmark_r2a_cli.py` 使用明确标记的 synthetic 图层与姿态，验证两个肩部
接触确实匹配并拉动关节，再生成20骨并精确回读。它不是模型检测、真实角色 GT 或 PSD
软件兼容性测试。数值测试另行覆盖位移/骨长约束、退化阻塞和父子 FK 精确重建。

输出仍为 `candidate_requires_review`、`authority:none`。R2-A 没有改变主工作台的
manual review门槛，没有将 Benchmark 决定升级为生产授权，也没有导出新的生产 RigIR。
后续需把候选接入已有 JointCandidate 复核入口，再通过合法决定更新 ResolvedProject；
生产 `policy_auto` 仍需独立策略及真实准确率证据。
