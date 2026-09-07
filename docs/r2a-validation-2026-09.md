# R2-A 技术验证（2026-09-07）

本次验收范围是规范姿态输入到未批准候选骨架，不是 R2 自动 region rig 整体验收。

| 验证 | 结果 |
| --- | --- |
| `python -m unittest discover -s tests -p 'test_benchmark*.py' -v` | 186项通过，52.027秒 |
| `python -m unittest tests.test_pose_runner_base tests.test_joint_optimizer tests.test_canonical_skeleton tests.test_quality -v` | 19项通过，0.331秒 |
| `npm test --prefix web` | 405项通过 |
| Synthetic CLI | 两个肩接触匹配且产生非零融合位移，生成20骨，全链精确重放及重复运行幂等 |
| 真实开发集缺姿态负例 | Alice、铃仙、琪露诺均 blocked、零骨骼、零批准权 |
| 可视检查 | Chrome实际渲染 synthetic HTML，检查源图、编号、颜色与20骨表格 |
| 独立代码审查 | 未发现阻塞项；输入镜像声明并非实际镜像识别结果 |

曾启动完整 Python discover，随后主动中止，未获得全量结论；未将部分日志计为全量通过。
初次定向命令误写不存在的 `tests.test_pose_runner`，已更正为 `tests.test_pose_runner_base`
并执行上表19项。没有执行 opt-in 官方 Spine Runtime，本次无新的 Runtime 或生产视觉证据。

外部生成产物位于 `../tmp/r2a-synthetic-v1/`（合成示例、报告、截图）和
`../tmp/r2a/`（三角色 pending 报告）；原始真实角色观测和 GT 均没有被代填。
日志 `../tmp/r2a-benchmark-tests.log`、`r2a-web-tests.log`、`r2a-full-tests.log` 不进入 Git。

新增核心位于 `asset/joints`、`runners/pose`、`benchmark` 独立小模块，文件预算测试通过。
历史 RigIR、P9/P10、Spine Adapter 和主工作台生产权限逻辑未修改。
下一步 R2-B：真实隔离 Pose Runner → 三开发角色原始观测 → 人工独立 GT →
旧基线/优化结果误差对照；随后校准阈值、接入现有 JointCandidate 复核并扩展十角色。
