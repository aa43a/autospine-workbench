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
