# 建立首批 Benchmark 与读取指标

此入口把已有素材盘点转为可校验、不可变的数据集，并保存工程划分与评测报告。
它不会批准 PNG↔PSD 对应、自动填写关节、或把输入检查算作绑骨完成。
需要 Python 3.11+；只有 `lint-inputs` 使用可选 analysis 环境中的 Pillow。

## 建立和冻结

在仓库目录运行，源文件保持在上级 `localset`。下面的输出是独立文件；已有不同
内容不会被覆盖。`--state-root` 是可选部署参数，放在子命令前。

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m autospine_workbench.benchmark intake --inventory docs/benchmark/inventory-2026-09.json --workspace .. --output ../tmp/benchmark/intake.json
python -m autospine_workbench.benchmark propose-split --manifest ../tmp/benchmark/intake.json --development-source png/爱丽丝.png --output ../tmp/benchmark/split.json
python -m autospine_workbench.benchmark freeze-split --manifest ../tmp/benchmark/intake.json --proposal ../tmp/benchmark/split.json --output ../tmp/benchmark/frozen.json
```

`intake` 逐字节检查 20 PNG 和 12 PSD 的 SHA、大小及画布头信息，成功后才发布
manifest；缺失或变化会输出包含具体 reason code 的报告，并返回非零退出码。
这不是图层质量、图片可绑骨性或坐标变换验证。

划分提案优先使用有 PSD 候选映射的原图，再按源 SHA 排序选择首批 10 个。
明确指定已检查过的 Alice 为 development，避免混入 holdout。结果为 3 development、
4 visible、3 holdout、10 reserve；同原图的两个 PSD 变体始终随该原图分组。
此策略依赖素材可用性，并非随机代表性抽样。其样本选择偏差必须随指标披露。

`propose-split` 不冻结；`freeze-split` 是明确的工程分配动作，不是人工标注批准。
提案绑定原 manifest，换来源后不能沿用；冻结后同样的分配幂等，改变分组被拒绝。
历史 manifest 由内容地址保留。另建版本必须保留可追溯关系，不能为提高成绩暗换 holdout。

## 检查开发集与生成空评测

```powershell
python -m autospine_workbench.benchmark verify-sources --manifest ../tmp/benchmark/frozen.json --workspace ..
python -m autospine_workbench.benchmark lint-inputs --manifest ../tmp/benchmark/frozen.json --workspace .. --output ../tmp/benchmark/development-inputs.json
python -m autospine_workbench.benchmark observations-template --manifest ../tmp/benchmark/frozen.json --code-commit (git rev-parse HEAD) --output ../tmp/benchmark/observations.json
python -m autospine_workbench.benchmark metrics --manifest ../tmp/benchmark/frozen.json --observations ../tmp/benchmark/observations.json --output ../tmp/benchmark/metrics.json
```

`lint-inputs` 默认只读取 development 原图。其阈值 alpha 8/32 的 bbox、透明度、
触边与画布比例只作为机器信号；全透明图阻塞，其余可疑情况警告，不宣称已检测
人体裁切、多角色、透视或肢体交叉。`--split` 可显式选择其它组；调参期间不使用 holdout。
原图与 PSD 画布不同，不能把这里的坐标直接填入 PSD 关节。

空 observations 的 records 为 `[]`，意味着所有角色尚未评测。首批完成率显示
0/10；P50/P90、抽查准确率、自动覆盖率均为 null，不会变成 0 秒或 100%。
首批、reserve、各 split 和全部 20 个分别报告，失败、阻塞、缺记录都保留在分母里。

## 录入真实评测

复制空 observations 到新文件，再为实际测过的角色填写 records。每行严格包含：

- `character_id`、对应原图 `source_sha256`；
- `status`：succeeded / blocked / failed / not_run；
- `reason_code`：失败、阻塞必填，其余 null；
- `review_seconds`：实际测量值或 null；
- `auto_adoption_audit`：null，或 adopted / checked / correct 三个真实计数。

正确数不能超过抽查数，抽查数不能超过采用数；零抽查的准确率为 null。
目前没有 eligible 候选分母，所以自动覆盖率始终 null，后续接入真实候选观测再扩展。
记录绑定 manifest、代码提交、profile 和目标版本；相同角色不能重复，源图不能串接。
这些是操作者提供的观测统计，尚未自动重放关联 PipelineRun 或核验人工抽查证据，
因此报告保持 authority=none，不是质量认证。重建验证可使用 `validate_metrics`。

现阶段 manifest 固定为 pending 标注：complexity、rights、关节和语义留空，
不允许将自动候选写成 ground truth。现可使用[坐标复核页](how-to-benchmark-mapping.md)
调整 PNG↔PSD 候选并保存无权威草稿；正式人工标注决定仍待开发。

## 工程边界

新代码位于 `benchmark/`，复用不可变文件写入原语，不修改 P9/P10 算法或已有预览。
数据集、提案、源验证、观测、指标、输入检查按内容地址保存；可导出到指定文件，
不需要用户复制数据集 SHA。报告不能替代官方 Runtime 验证或认证基线。
