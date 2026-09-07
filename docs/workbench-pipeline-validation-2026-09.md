# 主工作台 Pipeline / Review Queue 验证（2026-09-07）

基线：`dd1136e` 的项目级 CLI。本切片接入主工作台按钮、单线程异步请求、复核队列、
保存后续跑与 ZIP 下载。没有自动采用策略或新的 Runtime/发布权。

## 已交付边界

Review Queue v1 根据现有 setup-region 门禁细分 semantic、pivot、binding、joint、
split 和 rig 异常。包含固定 reason code、风险、证据图链接、回退与下游失效范围；
实体 ID 稳定，整个队列绑定当前三源地址与内容 SHA。队列是只读派生视图，不写决定。
已人工标记的 unobservable 仍按旧编译合同处理，不制造新的批准或阻塞语义。

Web job 只引用 PipelineRun。请求先持久化再交给单工作线程，最多 8 个活跃请求，
同一活跃输入去重。轮询只读状态；服务重启不自动重放遗留请求。取消先阻止后续步骤，
已开始的纯编译可先返回。关闭服务时先停止 automation，再保证原有 managers 释放。

下载验证 ZIP SHA、固定库存和 preview bundle 地址后，必须调用真实 P2 region
精确读回并比较每份文件字节。可重封的 job/journal 不能证明文件由编译器产生。
此只读复验可能增加下载等待时间，不发布或修改任何源工件。

UI 不接受用户输入 SHA，不显示 state-root。未保存、保存中或加载中禁用构建与下载；
项目/Resolved 变化丢弃旧响应。只对用户主动启动且停在复核的预览，在保存后能力
就绪时继续构建。刷新页面后需要重新点击；完整取消重试策略仍沿用 PipelineRun v1。

## 验证结果

| 检查 | 结果 |
| --- | --- |
| Pipeline/Queue/Web jobs/HTTP/旧 server/catalog/质量聚合 | 100/100，29.225 秒 |
| 下载补强后 jobs/HTTP/质量定向复验 | 17/17，11.439 秒 |
| Web 全量 | 400/400 |
| 最终 Chrome headless + 真实隔离 HTTP 服务器 | 构建、ZIP 下载、未保存门禁通过；无 page error |
| 1440×1000 与 390×844 视口 | 无横向溢出；移动画布高度稳定 |
| 工程预算 | app.js 1182→1175，index.html 400；未扩大 styles.css/project_store.py |
| 旧编译算法、历史 golden | 未修改；前一切片历史重放结果单独保留 |

早期聚合运行发现 index.html 超限，以及一次指定了不存在的测试模块名；修正后
聚合检查全绿，没有放宽门禁。最后的下载审计发现 journal/ZIP 同时重封可伪造输出，
已接回 P2 重建验证，并新增真实篡改反例。

实际浏览器曾发现移动画布自动高度与平移 ResizeObserver 形成倍增循环，Chrome
尝试分配 33554432px 高截图而崩溃。独立 responsive CSS 现为移动画布设置有界高度
和尺寸隔离；自动化脚本先断言页面/画布高度上限再截图，避免回归时耗尽浏览器内存。
触控入口至少 44px。

浏览器 smoke 使用合成的 reviewed P2 fixture，经真实编译生成 7349 字节 ZIP；没有
操作真实 A/B 人工决定，也没有启动 Spine 官方 Runtime。截图和下载在本地
`tmp/pipeline-workbench-browser-2026-09`，脚本为 `tools/check_pipeline_workbench_browser.cjs`。
需已安装 Playwright 与 Chrome，并指向隔离测试服务。服务端 fixture 在验证后关闭。

本次没有重跑全量 Python 或创建 certification tag。已有 20 PNG/12 PSD 原件不变。
下一步为独立 `policy_auto` 合同与指标，按异常频率推进自动语义及通用 Mesh/Weight。
