# Alice 与辉夜行走候选：局部修复和 Runtime

2026-09-27，接续同一校准策略，不改变骨骼轨迹、权重、纹理、固定顶点或几何门槛。

Alice 双腿同时烘焙 221 个槽位×时刻的局部修正，最大位移 1.414626px。
969 个密集 CPU 时刻全层通过；辉夜同样 969 时刻通过且零修正，输出骨架与
接触求解输入完全相同。实测确认两者 setup/骨轨迹不变、固定顶点移动为零。
修复工具支持重复 `--slot`，各槽位从同一未修正输入求解，最终统一验证，
不通过串行覆盖丢失先前槽位的变形。健康区域不添加零值修正时间轴。

| 角色 | 新官方 Runtime 时刻 | 最大脚端误差 | 最终踝代理接触 | 补充遮挡 |
| --- | ---: | ---: | --- | --- |
| Alice | 969 | 0.167190px | inferred_proxy_passed | 104 条冲突，无未测部件对样本 |
| 辉夜 | 485 | 0.250642px | inferred_proxy_passed | 122 条失败记录、110 个未测部件对样本 |

实际 Runtime 为 4.3.13，目标输出为 Spine 4.3.26。辉夜没有新增 deform 键，
因此捕获链生成 485 时刻，不把另行 CPU 的 969 时刻冒充 Runtime 帧数。
Runtime 证明采样顶点与非空未裁切画面；踝代理不证明鞋底接地。
新深度报告重新绑定来源、映射、捕获和骨架身份；没有应用绘制顺序提案。
辉夜缺测来自受限像素检查，不能视为无冲突。

## 工作台登记

- Alice：父任务 `motion-7c82795adde040c39ef1ffa40ea79c9f`，候选
  `c8d55e2a0c1f02e0765086132ec07bc18feef79fd8b4223c1b39be89eada59b3`，注册
  `0c71a20f4ffa02a042eb8756c0952d733f30c7a7923894decbee41fabf489ed2`。
- 辉夜：父任务 `motion-e33bb3e9380c476ba54d6fb75021e573`，候选
  `7237ddd29242c69633d6151cbd817253001f11e985ac5e3d809df2b1fc98196f`，注册
  `a061017aeda1f28734d34ce960013d3cfdbbb305878b234c1addac84bf883146`。

使用显式 `--unreviewed` 登记，不导入任何视觉决定；两份在线 stage-review
均为 revision 0、current null、current_applies false，播放器端点正常返回。
原基线和所有历史接受保留。已发出这两份精确候选的阶段复核请求，尚未获得结论。

产物：`E:/proj/unusual/localset/tmp/m4-walking-{alice,huiye}-runtime-v1/`，
各含 Runtime 报告、播放器、隔离包与独立 `depth-review.json`。
相关身份、注册和深度检查 13 项测试通过；不等于视觉验收或全 M4 完成。
