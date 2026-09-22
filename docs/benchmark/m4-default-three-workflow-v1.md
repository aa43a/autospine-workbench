# 三结构角色默认呼吸交付回归（2026-09-22）

来源为已导入的 `motion-c52561d5d07946539a8ca0da57e218e0`。三次均通过真实工作台按默认策略创建独立动作任务，完成构建、当前页播放器、源骨架同步和浏览器下载；没有继承旧候选的人工接受。

| 角色 | 新任务 | Runtime 帧数 | 实际下载文件数 |
| --- | --- | ---: | ---: |
| Alice | motion-0ee0bf6685264d1e999dfe854c1511ac | 1108 | 98 |
| 辉夜 | motion-45db86457ff44d14934c149cf5a4ecf0 | 1108 | 88 |
| 红美铃 | motion-37228bf7f02d455a87feb3f898888c8b | 1108 | 92 |

播放器身份与任务候选一致，起始、中间、结束三处共用时间轴检查通过。浏览器实际下载 ZIP 的文件集合与每个文件字节均和对应不可变候选一致。三项 readiness 仍为 `needs_changes`，不将交付成功等同于技术全通过或视觉接受。此前原 Breathing 的接受记录保持其原身份。

## 真实操作暴露的问题

红美铃第一轮在角色检查结束前超过工具 30 秒等待，没有提交。第二轮已成功创建任务，但 HTTP 提交响应也超过工具 30 秒等待；通过服务端任务及构建请求确认身份后，只跟踪同一任务，没有重启或重复提交。证据单独记为 `recovered.json`，不冒充浏览器完整收到了提交回执。

测试工具改为最多等待 120 秒，并在首次操作前写入独占 attempt 文件，防止意外重复执行。延长测试等待不是性能修复；角色选择及提交前验证延迟仍需定位与优化。

## 证据目录

- `localset/tmp/m4-motion-center/default-alice-breathing-v1`
- `localset/tmp/m4-motion-center/default-huiye-breathing-v1`
- `localset/tmp/m4-motion-center/default-hongmeiling-breathing-v1`：未提交的等待超时。
- `localset/tmp/m4-motion-center/default-hongmeiling-breathing-v2`：已存在任务恢复、播放器与下载证据。

这完成了三种结构的默认呼吸操作回归，不覆盖三角色八动作的全部质量验收。下一项优先修复慢校验对选择及提交响应的影响，同时保留 Reach/Squat 表示问题的限额验证计划；不以扩大等待时间宣布完整默认流程已达产品性能要求。
