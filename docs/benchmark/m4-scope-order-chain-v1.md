# Alice 覆盖区到顺序候选的实际包验证

2026-09-26。使用既有隔离覆盖区包 `8c4778d992af00da337710f8dc8c98a387915e94c9f0a894b16e4606fd066bdb`，将 layer-003-depth-001 的诊断三角形 0 在 1–3 秒置于 layer-006 前方。该选择用于执行链测试，不代表人工语义标注或推荐顺序。没有写入工作台草稿或接受记录。

得到独立包 `0b42c09f432a52c691ef0d8db53789c1164fd37c864f88ea96cacead9dab6af3`：27 个附件，737 帧官方捕获通过，几何通过，继承两项问题。Spine 目标 4.3.26，实际 Runtime 4.3.13。原报告字节保持一致，新候选 readiness 为 needs_changes；脚端轨迹和遮挡尚未重新验证。

隔离输出 `tmp/m4-scope-order-chain/alice-v1` 包含 plan.json、build.json、runtime/report.json、捕获 PNG、diagnostic-candidate.zip 和 verification.json。归档的 98 个文件均与不可变包逐字节一致；这验证离线打包，不替代 HTTP 下载或草稿提交接口验证，也没有覆盖完整 worker 的来源历史装配。

实际查看 external-motion-320.png：肩侧仍有白粉色透明边缘散点和不自然轮廓，没有据此通过视觉验收。旧结果及历史决定保留。8918 仍由 PID 25588 监听，未尝试绕过重启限制。

机器可读结果见同目录 m4-scope-order-chain-v1.json。M4 未完成，剩余整链在线操作、来源通用性和大动作质量继续独立验收。
