# M4 普通角色来源校验性能

2026-09-22。默认构建前，`character_ordinary.route_source` 原先为判断是否存在袖装任务而调用完整 `SleeveWebJobs.overview`。对红美铃，后者会触发袖装标注就绪检查和网格来源读取，尽管当前只需要知道任务是否存在。

改为 `has_job` 读取任务请求历史。任何同项目袖装任务（包括取消、失败、撤回或未完成）仍阻止普通路线回退；读取失败不当成不存在。实际袖装候选检查、角色输入校验、构建前后身份检查均保留，无跨请求缓存。

对照命令（仓库根目录，PYTHONPATH=src）：

```text
python tools/profile_character_route_guard.py imported-885b4d3d22ee151a0364ac499a419b8bd0e59699a7b27ee4f65f007eee551590 job-7d8ce666ea13487a953bdfa5258ea79a ../tmp/m4-motion-center/validation-performance-v1/hongmeiling.json
```

同进程交错运行旧／新／新／旧策略，不修改候选。旧策略单次 character.get 为 4.491、4.873 秒；新策略为 2.236、2.483 秒。四次均返回 needs_review，artifact 为 `fadde972f148b353592aaeebf75df151b9ef57032efaacde1773ea5a8754d28c`。这是本地函数耗时，不是 HTTP 提交延迟或动作质量证明。

31 项袖装任务、普通角色路线、整角色任务与动作重定向测试通过。新增测试覆盖不读取标注就绪状态、跨项目隔离、取消后历史保留及损坏请求拒绝。

仍需验证工作台实际选择／提交延迟，并处理提交路径重复校验。未改变 M4 的动作支持范围或任何人工验收。

## 工作台选择与提交实测

新增只读 `/automation/character/motion-target`：选择角色时只寻找当前任务并通过原 `get` 进行完整来源校验，不再生成整角色构建表单的全部选项。完整构建页面继续使用原 overview。没有候选返回空；过期候选仍返回 blocked；不回退到旧任务。

工作台提交期间明确显示正在校验和提交，禁止重复点击。真实 Chrome 单次默认提交创建 `motion-e63c5e9078fa4654b625e4415ac39b61`；选择到按钮可用 9.113 秒，点击到收到 202 回执 13.829 秒。前者还包含 UI 并行准备，不能等同于单接口耗时。完整回执、源动作与角色任务身份、排队截图保存在 `localset/tmp/m4-motion-center/validation-performance-v2/hongmeiling`。

这些等待仍偏长，尚未满足即时操作体验；未宣称性能问题全部解决。新增路由只读测试和来源失效测试通过。

任务完成后，Runtime 检查 1,108 帧、27 个槽位，几何失败记录为 0。新产物 `643d3e9bd7bccca01d92d21335b4b29886262b193a7bb7e5d342d559105820fd` 与之前红美铃默认呼吸候选一致；流程优化未改变输出内容。Runtime contact_status 仍为 not_evaluated，不用几何通过替代接触、深度或视觉验收。33 项相关测试通过。

真实浏览器同页播放、源骨架同步时间轴在起点／中点／终点核对通过，无脚本错误；实际下载 ZIP 的 92 个文件与不可变候选逐字节一致。readiness 继续为 needs_changes，旧异常未被清除。证据为同目录 browser-delivery.json、delivery.json 和截图。工作台 8918 已加载本次修复。
