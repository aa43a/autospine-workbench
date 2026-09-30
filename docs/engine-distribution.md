# 独立引擎分发与验证

Studio 客户端仓库继续只保存客户端。引擎源码和可选运行环境在本仓库的
`release/` 中生成独立工件；用户素材、项目状态及训练模型不进入这些工件。
安装后由 Studio 主进程启动和管理引擎，使用系统分配的本地端口，用户不需要
先运行工作台或填写端口。

## 源工件

开发者可用 Python 3.11+ 运行：

```powershell
python -B packaging/engine_distribution.py build --output release/AutoSpineEngine-new-version
python -B packaging/engine_distribution.py verify release/AutoSpineEngine-new-version
```

默认来源是确切 Git HEAD；`--commit` 只接受完整 40 位提交 ID。工具读取该提交的
archive，不读取未提交的源码或实验文件。只导出固定源码、工具、网页和 schema
范围，排除测试、缓存、PSD、项目状态、模型、Git 历史及历史角色集引用文件。
既有输出目录和 ZIP 都拒绝覆盖，失败产生的新目录保留以供诊断。

清单文件 `engine-distribution.json` 使用
`autospine.engine-distribution/v1`；源工件明确标为 `engine-source-only`。清单包含
source commit、平台、固定 `engine` 根及逐文件大小与 SHA-256，不包含绝对用户路径
或构建时间。清单自身不放入文件清单，外部交付记录其 SHA-256。ZIP 文件顺序和时间
字段固定，同一提交和工具版本可生成相同字节。摘要用于完整性校验，不是发布者签名。

源工件不包含 Python、Node、浏览器、依赖环境或模型，也不证明任一功能已经就绪。
`engine/DEPENDENCIES.json` 声明核心、PSD 解码、数值分析、服装求解、官方 Runtime、
捕获、Pose、Kimodo 及 FBX 的各自前提。DWPose 许可证文本仅用于归属，模型不打包；
仓库尚未声明源码发布许可证，工件不授予公开重分发权利。

## 核心运行环境工件

`packaging/prepare_core_runtime.py` 接收已经核对上游摘要的官方 Python embeddable ZIP
和固定 wheelhouse，另建 `engine-core-runtime` 工件。它不复制本机全局 Python 或
site-packages，不执行安装脚本，不下载模型。官方来源及 SHA、依赖 wheel 声明和许可
文件记录在 `runtime/PROVENANCE.json` 和相应许可证中。

核心包只补充 Python、PSD 解码、NumPy、SciPy 和 schema 依赖。Pose 模型、Node/Spine
官方验证环境、浏览器捕获、Blender 与 Kimodo 仍是独立能力。不能将这个包称为已经
完整验收的新电脑 S1–S6 安装器。

## 真实启动检查

```powershell
python -B packaging/smoke_engine_distribution.py `
  --bundle release/AutoSpineEngine-new-version `
  --python C:/absolute/installed/python.exe `
  --output release/test-results/new-empty-state-check
```

检查实际工件源码建立真实 HTTP 服务，新建隔离 workspace/state，核对健康会话、空
项目列表、网页入口，并只关闭自己创建的进程与端口。启动和关闭前后工件库存保持不变。
使用源工件时仍调用明确选定的既有 Python，报告不会将它标作清洁电脑验证。

对核心包指定包内 `runtime/python/python.exe` 时，额外核对隔离搜索路径、关闭用户
site、忽略外部 PYTHONPATH 诱饵及精确依赖版本；执行生成的一像素 PSD 解码、真实
PSD worker（未添加 `-B`）、NumPy/SciPy 标量求解和 schema 校验。测试使用单独的输出
目录，工件不得因 worker 生成 pycache 而改变。这些是环境证据，不是角色导入、关节
人工复核、布料动作质量或官方 GPU Runtime 验收。

## 2026-09-30 源工件证据

源提交 `69ac9dbd1242d501ba41cb8ece4f0adf393c39e4`：

- 3,278 个文件，16,266,409 字节。
- 清单 SHA-256：`063adbf92c23d5d0aa9bc7dbcf121431087fcfb3294a4d36b9b8aa0e8208c8cb`。
- ZIP SHA-256：`d48d06568827d12ee780e0259c3e7196cc1aa6cb7c7237584ecac6b098d093d3`。
- 两个独立输出目录的清单和 ZIP 摘要完全相同。
- `release/test-results/engine-source-smoke-v1/report.json`：6 项实际空状态检查通过，
  Windows Job Object 自有进程树、退出码 0、已关闭监听、工件未变。

`tests.test_engine_distribution` 检查路径、排除范围、作用域、库存损坏、真实 Git
快照可复现及未提交内容不进入工件。`tests.test_studio_core_runtime` 使用明确的合成
输入验证 hash、平台、路径、别名和失败保留；合成 Python 文件不会执行，也不作为
可运行环境的证据。完整新素材操作、模型推理、动作质量与另一台新电脑验收仍另行执行。

核心 v5 的 `release/test-results/engine-core-smoke-v5/report.json` 已完成 9 项实际检查。
使用包内 Python 3.14.3，隔离/忽略环境均启用、用户 site 关闭、字节缓存关闭；全部
Python 搜索路径及被调用依赖的安装根位于工件内。直接和真实无 `-B` 子 worker
均精确解码一像素 PSD，数值求解与 schema 校验通过，退出后库存仍为 4,916 文件、
182,260,894 字节，清单摘要为
`2dfb0c0b5a4db8840ec8a924d3301d5708b8bd58c7528d86e8ac7715a65885fc`。
psd-tools 的一条 `Invalid signature` 诊断日志保留；输出像素和审计核对通过，不把
这一环境检查外推为任意 PSD、整角色动画或新电脑全部能力通过。

## 核心 v5 独立 ZIP

已有冻结目录可只读归档，拒绝覆盖既有 ZIP，也拒绝将 ZIP 写进工件目录：

```powershell
python -B packaging/engine_distribution.py archive `
  release/AutoSpineEngine-core-69ac9dbd-py3143-v5 `
  --output release/AutoSpineEngine-core-69ac9dbd-py3143-v5.zip
```

本次实际产物为 `release/AutoSpineEngine-core-69ac9dbd-py3143-v5.zip`：

- ZIP 大小：69,687,801 字节。
- ZIP SHA-256：`84c737b9c6309305f380286fa6f92a09b20d5673ad60695e6783000a62e9d19c`。
- 4,917 个成员：原清单中的 4,916 个文件，加 `engine-distribution.json` 本身；
  解压总字节数为 183,242,857。
- 归档前后完整目录库存均为 4,916 个清单文件、182,260,894 字节，清单摘要均为
  `2dfb0c0b5a4db8840ec8a924d3301d5708b8bd58c7528d86e8ac7715a65885fc`。
- ZIP 内逐成员名称、普通文件属性、未加密状态、大小、CRC 和 SHA-256 均校验通过，
  没有多余目录、客户端、用户素材、状态或模型。原 v5 目录未修改。
- 归档工具增补后，既有 17 项 source/core 单元测试再次全部通过；其中真实 Git
  快照测试同时检查只读归档、拒绝覆盖以及禁止写入工件内部。

ZIP 仍然只属于 `engine-core-runtime`：包含独立引擎源码、Python 和核心依赖，
不包含 Pose 模型、Node/Spine 官方检查环境、浏览器、Blender 或 Kimodo。摘要不是
发布者签名；完整新电脑工作流验收依旧单独执行。

## Node 控制输入与真实 PSD 导入对照

2026-09-30 使用同一冻结 v5 的 private Python 3.14.3，实际 `create_server`、
HTTP `asset-imports`、生产 `PsdImportJobs` 的单线程池和真实 PSD worker，导入
两层、96×128、50,630 字节的独立测试 PSD；输入 SHA-256 为
`b015ed77d8ee9dfe8b55038bea3948947a12fac9292a991701e340b0ce3379ff`。
每个实验新建隔离 workspace/state，并在任务提交后 2、10、30 秒记录任务、
本次进程树及线程栈。没有加载已有用户项目，也没有借用全局 Python 解码器。

| 条件 | 2 / 10 / 30 秒任务 | 真实 worker 用时 | 输入管道与退出 |
| --- | --- | --- | --- |
| 普通独立服务 | 三次均 succeeded | 1.439 秒 | 正常关闭本次服务，退出码 0 |
| Node 三管道，常驻读取控制 stdin，worker 默认继承 stdin | 三次均 running/parsing，尚无 decoded 文件 | 31.967 秒 | 父输入在 32.004 秒关闭后恢复，最终 worker 退出码 0；30 秒门槛仍记失败 |
| 同一 Node 管道及读取线程，仅诊断 worker 的 stdin 改为 DEVNULL | 三次均 succeeded | 1.439 秒 | 管道仍打开时完成，正常退出码 0 |
| 同一 Node 管道仍打开，不启动常驻 stdin 读取线程 | 三次均 succeeded | 1.482 秒 | 管道仍打开时完成，正常退出码 0 |

证据分别在 `release/test-results/core-v5-two-layer-service-v1/`、
`core-v5-two-layer-pipe-watch-v1/`、`core-v5-two-layer-pipe-devnull-v1/`、
`core-v5-two-layer-pipe-no-watch-v1/`。Node 对照保留 `stdout.log`、`stderr.log`、
父子进程报告及 2/10/30 秒线程栈；正常服务报告也保留真实 worker stdout/stderr。
测试失败记录不删除，也不以关闭后的成功改写 30 秒失败结论。

阻塞时 HTTP 查询仍正常，`psd-import_0` 停在 `subprocess.communicate` 的输出读取
线程 join；任务锁未在执行子进程期间持有。对照把问题定位到长期读取的父控制输入
被子进程继承这一交互，不支持将原因归为 PSD 解码或 Pillow 的一般性能。
修复应由 **Studio launcher** 分离父进程关闭控制输入与默认子进程标准输入；本次
仅完成定位，未修改引擎生产代码或冻结 v5，也不声称已经验证客户端修复。

两个参数化诊断 fixture 位于 `tests/fixtures/psd_service_diagnostic.py` 和
`psd_service_pipe_diagnostic.mjs`，只允许在本引擎仓库的 `release/test-results`
下创建全新输出，拒绝既有输出及链接路径。它们在测试进程中包裹标准库的
Popen/run 以记录原始命令；明确的 devnull 对照只改变 stdin，不替换解码器。
不将这些测试 hook 当作实际产品修复或任意外部执行接口。

四组本次进程均已结束，输入 PSD 字节未变。结束后完整工件库存再验证仍为
4,916 文件、182,260,894 字节和原清单摘要 `2dfb0c0b5a4db8840ec8a924d3301d5708b8bd58c7528d86e8ac7715a65885fc`；
17 项分发/core 单元测试再次全部通过。它们不代表另一个全新 Windows 电脑已完成
全部 S1–S6，也不包含角色视觉验收。
