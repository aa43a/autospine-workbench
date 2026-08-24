# AutoSpine Workbench 架构与质量门禁

本文约束的是持续开发方式，不是一次性重写计划。任何新功能都先进入版本中立合同和可复现工件，再接 UI 或特定 Spine 版本适配器。

## 不变量

- PSD、See-through audit 和导出的 PNG 是不可变输入；工作台只写自己的 state、analysis 和 build 目录。
- 每个自动分析结果记录输入哈希、算法版本、配置和产物哈希。HTTP 请求只读取已完成工件，不在线运行重型分析。
- 人工决定与模型证据分开保存。人工可以接受、调整或拒绝候选，但不能改写模型置信度。
- setup pose 先通过 region attachment 验证。只有 region 无法满足连续弯曲时才引入 mesh、weight 和 deform。
- RigIR 是版本中立边界。目标 Spine 版本只存在于 adapter 内；未知 attachment、constraint 或 timeline 必须明确失败。
- 保存使用 optimistic concurrency；每个成功 revision 都可追溯，不覆盖历史证据。

## 模块边界

依赖方向保持单向：

```text
contracts / value objects
        ↓
audit repository ── analysis artifacts ── override history
        └───────────────┬──────────────────┘
                        ↓
              resolved project snapshot
                        ↓
             manifest / RigIR compilers
                        ↓
        semantic validators / probe runners
                        ↓
              target-version adapters

server → application services only
web    → HTTP contracts only
```

- `project_store.py` 只保留发现项目和协调 application service 的 façade 职责，不再承载分析算法、持久化实现或 Rig 编译。
- `server.py` 负责 HTTP、输入大小、loopback 安全和错误映射，不实现领域规则。
- 前端分为 API、authoring state、保存事务和各 stage view；view state 不得污染 revision draft。
- 外部姿态模型只能通过 canonical pose observations 进入；alpha 几何只读取 resolved layer 与固定 PNG，融合结果必须保留原始 pose 和未标定分数语义。
- COCO17 raw 输入、adapter、canonical pose、人工评估和候选工件分开内容寻址；坐标反镜像、左右标签交换、视角和镜像声明不得合并成一个隐式开关。
- 离线命令最终按 `import-pose`、`evaluate-pose`、`materialize-manifest`、`analyze-joints`、`compile-rig`、`run-probes`、`validate-rig` 和 `export-spine` 划分。

## 文件长度预算

生产源码的硬上限为 400 个物理行。新文件超过 300 行时就应评估按职责拆分；函数通常不超过 60 行，超过 100 行必须先拆解或在评审中记录理由。

当前四个历史单体采用 ratchet：只允许缩短，不允许超过测试中记录的当前上限。

| 文件 | 当前上限 | 拆分目标 |
| --- | ---: | ---: |
| `web/styles.css` | 1713 | 每个主题/布局文件 ≤ 400 |
| `web/app.js` | 1349 | façade ≤ 250，模块 ≤ 400 |
| `src/autospine_workbench/project_store.py` | 838 | façade ≤ 300 |
| `src/autospine_workbench/server.py` | 416 | HTTP adapter ≤ 300 |

`tests/test_quality.py` 自动执行上述硬上限与 ratchet。JSON Schema、文档和生成工件不套用源码行数上限，但仍应按版本和领域拆分，禁止手工复制生成文件来规避检查。

## 变更与提交

1. 先写失败测试或可重现 fixture。
2. 一次提交只完成一个可回滚能力；合同迁移与消费方更新可以同提交，但不要夹带格式化全库。
3. 每阶段运行完整单元测试；涉及图像或动画时额外保存固定视角、固定时间点的数值报告和代表性截图。
4. schema 通过只证明结构合法；跨引用、权重和骨架拓扑必须再经过语义验证器。
5. 任何迁移先读旧格式并产出新格式，经过至少一个发布周期后再讨论删除兼容路径。

## 完成门禁

- setup：画布、原点、side 语义、draw order 和 region 合成回归通过。
- visual：抬臂、屈肘、抬腿、屈膝探针在极值帧无明显断层、翻三角或越界。
- runtime：目标 adapter 的能力矩阵明确，未支持特性 fail loud；产物不依赖伪造版本字段。
- provenance：输入、analysis、override revision、manifest、RigIR 和 probe 报告均能由哈希串联。
