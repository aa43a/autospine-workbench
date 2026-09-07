# Spine 4.3.26 适配（2026-09-07）

编辑器导入修正：默认下载现附 `editor/skeleton.json`（相对图片目录 `./images/`）
和逐附件原始 PNG。完整解压后导入这份 JSON；根目录 JSON/Atlas/PNG 继续用于 Runtime。
原包只有图集，编辑器导入会显示 MISSING，参见
[官方导入指南](https://us.esotericsoftware.com/blog/Importing-skeleton-data)。
编辑器文件是从精确预览及已验证 P2 原图派生的下载内容；不改变运行时工件、历史
source/bundle 地址或旧任务回执。回执 `zip_sha256` 仍指封存的五文件 Runtime ZIP，
下载接口验证它后附加编辑器资源，因此最终下载字节与该封存 ZIP 不同。

主工作台与 `python -m autospine_workbench.automation preview` 默认目标为 4.3.26。
UI 版本选择器和 CLI `--target-version 4.2` 保留原输出。命名为 compile-spine42
的历史认证命令继续使用 4.2，不把历史证据重新标记为 4.3。

4.3.26 是 2026-09-07 发布的稳定编辑器版本，不是旧的同名 beta。
依据：[官方更新记录](https://esotericsoftware.com/spine-changelog)。
编辑器和 npm Runtime 的 patch 独立：目标 JSON 为 4.3.26，当前所记录的
`@esotericsoftware/spine-player` 版本是 4.3.13；本切片没有安装或执行该 Runtime。

独立 `targets/spine43` 包负责合同、编译和语义/跨文件校验。依据官方
[4.3 SkeletonJson 读取器](https://raw.githubusercontent.com/EsotericSoftware/spine-runtimes/4.3/spine-ts/spine-core/src/SkeletonJson.ts)，
4.3 使用统一 constraints 数组；本适配只接受无约束的已支持 RigIR 子集，
不会把旧 IK/physics 字段静默透传。共用坐标投影和 atlas/PNG 校验原语，
目标 profile、JSON header/hash 和 validator 独立。纯适配层支持 region、
现有 weighted mesh 与配对 P5 骨骼动作；普通用户工作流仍只输出 reviewed region setup。

新 engine 为 `region-spine-preview-spine43-4.3.26-v1`，存储于独立的
`region-previews-spine43` 命名空间，source/bundle 使用 `spine43-v1` schema。
4.2 的 engine、source schema、bundle digest 域和地址保留原值。
旧持久 Web receipt 缺少 target_version 时只按 4.2 解读。
新请求省略 target_version 时默认 4.3.26；后台回执明确记录实际目标。

重用和下载均从精确 P2 源重新编译，并逐字节比较目标工件。
切换目标会丢弃旧轮询及下载入口；未知版本、跨目标 run 和重封的错误 skeleton
必须失败。QA 的 `runtime_status` 保持 `not_run`，不会产生认证或发布权。

## 验证记录

相关 Python 聚合回归 120 项通过，Web 404 项通过，维护性门禁与 diff 检查通过。
新增适配包最大源文件低于 300 行，历史 `app.js`、`styles.css` 和 `project_store.py` 未增加。

隔离 reviewed fixture 的真实 Chrome smoke 通过：默认 4.3.26 下载 7506 字节 ZIP，
切换 4.2 后下载 7349 字节 ZIP，直接解析两份 skeleton header 均匹配所选版本。
桌面/移动无横向溢出、无页面异常，未保存编辑仍禁用构建/下载。
截图与报告保存在本地 `tmp/pipeline-workbench-browser-spine43-2026-09`；测试服务已关闭。

真实 A/B 的旧 4.2 preview 按 `pipeline-preview-smoke-2026-09.json` 中全部输出 SHA
完成精确重放；基于同一 P2 构建 4.3.26 后，两版 atlas PNG 逐字节一致。
新 4.3.26 bundle 地址：

| 项目 | Bundle SHA256 |
| --- | --- |
| seethrough_output | c8ab7e1f9fe34a8594a9a653d2ac322dde83e9b6d633f8b821042ad4d03ef61a |
| seethrough_output_5 | 071578a21f17865c6ac65f60d4021482d79cabfa463ef9393fd9e6ba41e6e438 |

这些是 reviewed region setup 预览，不改变 B 在其它能力上的不可观测门禁。
新测试覆盖版本独立幂等、旧 receipt 重开、目标切换迟到响应、跨版本重封拒绝，
以及 Mesh UV/索引/权重数组的非法类型与非有限数。未运行官方 4.3 Runtime，
未重跑全量历史 Python suite，也未创建新的认证标签。
