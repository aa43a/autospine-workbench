# PipelineRun v1：项目级编排与精确内核隔离

日期：2026-09-07。状态：已实现首个 `region-spine-preview` 操作。

## 决策

新功能位于 `automation/`。复用 current project 解析、拆分 materializer、Manifest/P2
编译和 Spine 4.2 纯 Adapter，不移动旧 P9/P10 模块、不向 leg-only P3 v1 添加语义。
P6 的精确输入合同要求 P3 地址，不能把 P2 region rig 伪装成 P3；因此使用独立的
`region-previews` namespace、bundle hash domain 和严格 source triple。

`PipelineRun v1` 绑定项目、profile、引擎版本和三个源地址：resolved、manifest、输入
资产身份。run ID 由这些值确定。各步只引用旧工件身份，编排记录不产生发布权。
步骤固定为 resolve-project、build-region-rig、compile-spine-preview。

语义 validator 验证闭合字段、地址、步骤前缀、状态、事件链接和内容哈希；JSON Schema
表达静态形状。状态由第一个未成功步骤派生；完成、取消均为终态。
pending/running 可进入 blocked、needs_review 或 failed；显式 resume 恢复未完成步骤。
最多 1024 次转换，超过上限明确失败，防止无界日志读回。

## 持久化与并发

每个 run 使用连续编号的不可变状态快照，持有前一快照 SHA。独占发布文件实现 CAS，
不存在可以直接覆盖的 mutable head。缺号、额外文件、非 canonical JSON、非法转换和
篡改均拒绝读回。临时文件不在事件目录；中断遗留 staging 不参与历史判定。

运行执行使用独立 OS 文件锁，进程退出自动释放。取消通过 journal CAS 生效，工作进程
不能覆盖取消后的状态。已经开始的纯编译可能留下完整内容寻址工件，但不会获得发布权。
恢复先精确读回已经完成的步骤，再继续缺失步骤；不会信任 journal 里的 succeeded 字样。

用户下载是确定性 ZIP，逐文件来自重建验证后的 byte snapshot。同名不同内容的用户
文件禁止覆盖。独占链接发布要求状态目录和下载目的目录支持本地文件锁及硬链接；
不支持的文件系统返回结构化失败，不降级为覆盖写入。

## 快照与能力

project snapshot 在临时目录处理 split 资产，entry/yield/exit 和每步发布前后检查
current resolved 与源文件身份。能力查询不发布工件。能力报告描述当前 setup-region
操作的支持范围，不覆盖旧精确入口对 mesh/motion 的支持。

production_review 在结构复核未完成时暂停；draft_auto 可保留诊断 rig，但仍不能把
manual-required QA 改成 passed。certification_exact 引导用户使用旧精确认证入口。
原 CLI 切片不含自动决定或 UI。后续主工作台切片在 façade 外新增 Web job 单线程
调度与 setup-region Review Queue；仍没有自动决定，也不使用 Runtime 执行许可。

## 验证与后续

新增测试覆盖状态机、CAS、执行锁、完整 P2 到 Spine byte 重建、输入漂移、失败恢复、
取消优先、工件篡改、无 SHA CLI 和不覆盖下载。固定 RGBA fixture 的源像素计数与
setup RGBA hash 提供数值检查；不新增或冒充官方 Runtime 视觉 golden。

主工作台 Build Spine Preview 和 setup-region Review Queue 已通过独立 Web job façade 接入。
自动采用、通用 Mesh/Weight、AnimationIR 按产品路线继续；旧精确证据仍原位保留。
