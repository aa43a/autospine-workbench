# PipelineRun / region 预览切片验证（2026-09-07）

历史检查点：`dd1136e`。下述范围为当次 CLI 切片，后续 UI 进展见 current-state。

范围：AS-003、AS-004 与 AS-005 的 CLI 基础。普通用户不需要输入 SHA；主工作台
按钮、统一 Review Queue、自动采用与后台自动续跑不在本次已交付范围。

## 自动验证

| 检查 | 结果 |
| --- | --- |
| 新 pipeline、capability、region preview、CLI、质量检查 | 60/60 通过，13.608 秒 |
| A/B 历史负向边界 | 2/2 通过 |
| 显式开启真实 P3/P4/P5/P6/seam golden 重放 | 11/11 通过，123.921 秒 |
| diff whitespace | 通过 |
| 官方 Runtime 新采集 | 未运行，未伪造视觉 golden |

首轮常规聚合检查为 71 项、66 通过、5 个 opt-in 跳过；随后开启真实重放。
沙箱下重放曾因 Windows 长路径 `PermissionError` 出现 10 个子例错误；相同代码在
正常权限下重跑全部通过，没有为通过测试放宽旧 reader 的安全检查。

新增测试覆盖确定性输入身份、闭合 Schema、状态转换、历史重放、真实 CAS 并发、
进程崩溃释放执行锁、取消优先、精确恢复、source drift、工件篡改、ZIP 幂等与
不覆盖用户文件。Spine 检查使用真实 P2 编译和 Adapter，检查 setup RGBA 身份及
源像素保留；测试替身只用于故障和中断注入。

本切片未修改旧生产模块、历史 golden 或质量 ratchet。新增生产文件最长 177 行。
未重跑完整 Python/Web 基线：旧全量报告仍见 [基线记录](baseline-tests-2026-09.md)，
不能把本切片定向测试视为最终 certification tag 验收。

## 真实项目 smoke

从 current A/B 项目直接调用新 CLI；生成内容保存在独立 `region-previews` namespace，
ZIP 放在 workspace 上级 `tmp/pipeline-preview-2026-09`。运行回执不输出本地路径。
准确结果和文件摘要见同目录的 `pipeline-preview-smoke-2026-09.json`。

这是静态 region setup 输出。B 的既有四条 unobservable 下肢接缝继续保留为负例；
允许 setup region 预览不代表动态 Mesh/接缝、Runtime 或正式导出已获准。

下一步为主工作台按钮及统一 Review Queue；操作说明见
[按项目生成预览](how-to-build-region-spine-preview.md)。
