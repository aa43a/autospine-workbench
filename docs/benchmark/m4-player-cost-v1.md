# Reach 完整角色播放器成本对照

2026-09-23，本机 Chrome 153.0.8010.54，Windows、i5-14600KF、20 逻辑处理器。使用 headless SwiftShader，画布 616×1062。同一 4 秒动作，预热 5 次后测量 60 次交错正向/反向 seek，包含 WebGL `finish`。本地路由提供不可变文件，未经过生产 HTTP 服务，不能据此宣称网络首帧性能或硬件 GPU 帧率达标。

| 项目 | 父候选 | 连续普通裁剪与近端材料候选 |
| --- | ---: | ---: |
| 完整角色槽位 | 26 | 503 |
| scene.json 字节 | 21,569,390 | 38,719,045 |
| 页面开始加载至 ready | 490 ms | 956 ms |
| seek 中位耗时 | 0.5 ms | 1.4 ms |
| seek P95 | 0.8 ms | 2.8 ms |
| seek 最大耗时 | 1.2 ms | 3.1 ms |

父候选：`21969ed99dd41e85171f52842fc4754a8d8c4bd425fd722cf87a78ce94b9d437`。
实验候选：`29b06d4cecbbe47387cdce5652c1cbe2e6090a0bb8d62aab6e6b7e1e5d7a546b`。

此前 478 槽位指隔离手臂；本次测量完整角色为 503 槽位。场景文件是播放器资产，不是导出 ZIP 包体。页面 ready 不是显示器实际呈现首帧时间，seek 也不是持续播放帧率。单次对照只提供基线，不冻结通用性能预算，不默认采用该表示。原肩部轮廓与遮挡验证缺口保留。

复现：设置 `PLAYWRIGHT_MODULE` 指向本地 playwright-core，然后运行 `tools/check-motion-player-cost.mjs`，两个输入目录分别为 `localset/tmp/m4-motion-center/reach-root-ordinary-v1/{before,after}/runtime`。原始 60 次采样及设备信息位于仓库 `tmp/m4-player-cost-{before,after}.json`。

同日常驻工作台已在确认无活跃任务后重启，155 条动作任务状态保持不变，Kimodo 配置仍可用；生成重试来源记录的后端更新已加载。未重新生成模型动作、未新增视觉接受。
