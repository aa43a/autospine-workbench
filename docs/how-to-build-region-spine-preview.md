# 按项目生成 Spine region 预览

本入口适用于已经导入工作台的 See-Through audit。它自动读取当前项目，构建缺失的
Layer Manifest、P2 region rig 和 Spine 4.2 setup 预览，无需手工填写内容 SHA。
本切片提供独立 CLI；主工作台按钮、后台自动续跑和统一 Review Queue 尚未接入。

## 构建和下载

在仓库目录中运行；`<project-id>` 使用工作台现有项目 ID：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m autospine_workbench.automation capabilities <project-id>
python -m autospine_workbench.automation preview <project-id> --output preview.zip
```

默认使用仓库上级 workspace 和仓库内 `workspace` 状态目录。使用自定义目录时，
把 `--workspace`、`--state-root` 放在子命令之前。这些是部署选项，回执不会显示本地路径。

成功生成的 ZIP 包含 `skeleton.json`、`skeleton.atlas`、`skeleton.png`、`source.json`
和 `qa.json`。可解压检查或交给支持 Spine 4.2 的预览工具。当前只有 setup，没有动画。
已有同内容 ZIP 可重复使用；同名不同内容文件会返回 `pipeline_output_exists`，不会覆盖。

默认 `production_review` 要求项目通过现有人工复核。未完成时返回 `needs_review`，
在现有工作台修复关节、图层语义、pivot 和绑定复核后再次运行同一条命令即可。
新 authoring revision 产生新的输入身份和 run；旧运行记录保留。

## 草稿、恢复和取消

```powershell
python -m autospine_workbench.automation preview <project-id> --profile draft_auto
python -m autospine_workbench.automation preview <project-id> --resume --output preview.zip
python -m autospine_workbench.automation status <run-id>
python -m autospine_workbench.automation cancel <run-id>
```

`draft_auto` 可构建仍待复核的诊断 rig；该 rig 不会绕过旧 Adapter 的 QA 门禁生成
Spine 预览。已经完整复核的项目在草稿模式下也能成功生成预览。

中断时，运行停在最后一次写入的状态。`--resume` 会重新验证已经完成的工件，并只继续
未完成阶段。活跃进程持有执行锁，另一进程无法抢占。相同项目输入、profile 和引擎版本
对应同一 run，重复成功请求会读回复验已有预览。

取消是终态，同一输入请求不会重新执行；取消不会删除已生成工件，也不强行终止当前
纯编译函数，但后续步骤不会继续提交。当前没有“取消后新建尝试”功能。需要继续时须
使用产生新身份的实际项目修订，不能伪造修订或手改 journal。

`status` 读取运行历史，不声称工件仍然有效；再次 `preview` 或下载会精确重验工件。
运行中的源图或 authoring 变化返回 `project_changed_during_snapshot`；下一次请求重新
读取 current 项目，不会把旧输入的输出接到新身份上。

## 状态和权限边界

退出码：成功/能力报告 `0`，失败 `1`，等待复核/阻塞/尚未完成 `2`，取消 `3`。
失败回执使用结构化 `reason_code`；具体阻塞原因在对应 step 或 capability items 中。

所有新回执和预览的 `authority` 固定为 `none`。QA 包含 setup 重建、旧 P2 精确读回和
Spine 跨文件验证；`runtime_status: not_run` 表示没有启动官方 Runtime，也没有完成
逐帧视觉验收。`can_export_spine: false` 表示没有正式发布权，和可下载 setup 预览不同。

`certification_exact` 在本入口返回 `certification_exact_entry_required`。认证继续使用
原有 P9/P10 精确链。新编排不改变旧 P2/P3/P6/P9/P10 工件、hash、golden 或批准决定。

参见 [PipelineRun 设计决策](adr/pipeline-run-v1.md) 和
[自动化路线](automation-roadmap-2026-09.md)。
