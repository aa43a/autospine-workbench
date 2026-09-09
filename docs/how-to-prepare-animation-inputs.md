# 从新 audit 准备动画来源

主工作台的“准备动画来源”把当前 audit、真实姿态推理和关节复核连起来。操作者不需要提供 SHA、模型路径或寻找中间 JSON。
当前支持尚未登记且没有作者校正（revision=0）的项目。已有登记继续沿用原来源；有人工校正但尚未登记的项目明确阻塞，避免丢失编辑。

## 操作

1. 在主工作台选择新 audit 项目，找到可变形动画预览区域。
2. 点击“准备动画来源”。页面依次显示准备图层来源、运行真实姿态检测、登记待复核来源。
3. 完成后会自动展开关节复核，将全部 17 点加载到画布。拖动或明确确认关节，无法确定的点保留不可观测状态。
4. 保存关节复核，继续绑定、动画候选构建与异常检查，参见[动画候选指南](how-to-build-animated-spine-preview.md)。

初始终态是 `needs_review`，不是错误：来源已经准备好，但没有任何点被自动确认为人工标注。
检测置信度不代表准确率；辅助标注不能用于独立 GT 精度声明。这里不会自动提交关节、绑定或预览构建。

可以取消正在准备的任务。推理子进程由 Runner 终止，登记前再次检查取消和输入变化。
服务重启后未完成任务显示 `preparation_interrupted`，点击重试重新检查来源；完成登记后的重试复用来源，不再次推理。
已完成登记后到达的取消不会把结果伪装为未登记。页面终态停止轮询。

## 维护者配置隔离 Runner

核心环境不安装 ONNX Runtime、OpenCV 等 GPU／推理依赖。服务只调用明确配置的独立 Python；模型固定为当前 DWPose profile，并校验权重 SHA 和尺寸。
此入口不下载模型，不接受 HTTP 提交的可执行文件或模型路径。准备好现有隔离环境和权重后，在启动服务的 PowerShell 中设置：

```powershell
$env:AUTOSPINE_POSE_PYTHON = 'E:/path/to/pose-env/Scripts/python.exe'
$env:AUTOSPINE_POSE_MODEL = 'E:/path/to/dw-ll_ucoco_384.onnx'
$env:PYTHONPATH = (Resolve-Path ./src).Path
python -m autospine_workbench serve --host 127.0.0.1 --port 8918 --workspace .. --state-root workspace --web-root web
```

配置无效、依赖缺失、模型不符、超时或输入漂移都返回结构化 reason code。公共响应不泄露本地环境路径。
当前单 worker，最多 8 个活跃任务；重复点击同一输入合并为一个任务。原始输出、请求和日志保存在本地状态目录供调查。

## 数据边界与验收范围

新增 `project-audit-source/v1`、`project-semantic-candidates/v1`、`animated-input-registration/v3`。
来源快照绑定 audit、合成图和每个图层的真实字节及画布尺寸；最终登记在项目事务中复查当前输入。
所有候选 `authority=none`，登记 `production_authorized=false`，全部绑定初始为 pending。
它不声称原始 PNG 与 PSD 已人工匹配，也不修改 benchmark 角色分组或 holdout。

2026-09-09 实测四个可见测试 audit：

| 项目 | 图层 | 画布 | 加载关节 | 初始已复核 |
| --- | ---: | --- | ---: | ---: |
| lumia | 22 | 1280 × 1280 | 17 | 0 |
| huiye | 21 | 1280 × 1280 | 17 | 0 |
| uuz | 23 | 1280 × 1280 | 17 | 0 |
| yaomeng | 24 | 1280 × 1280 | 17 | 0 |

露米娅通过真实浏览器准备、自动加载、无自动确认请求及终态停止轮询检查。
精确登记身份见[本次实测记录](benchmark/project-input-preparation-2026-09-09.json)。重启服务后可读取完成回执，重复准备复用同一登记且未新开模型推理。
Web 全量 432 项、Python 选定回归 67 项通过；随后补充合成项目的全 17 点复核到 61 帧动画包回归通过，并复跑受最终回执加固影响的 12 项测试。未运行整个 Python 测试库。
这四个项目尚未完成人工结构复核，也没有新的 Mesh 或官方 Runtime 通过声明。
R2-C 下一步是可见测试集的明确复核、失败分类和人工耗时采集，再建立自动采用策略校准；三个人工隔离的 holdout 保持不调参。
