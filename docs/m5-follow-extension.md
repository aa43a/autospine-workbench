# M5 随动扩展（2026-09-30）

## 上游更新与本次取舍

核对 Anime2.5DRig 的 2026-09-23 v2.0，固定提交
`7ddbd9943ea3152561b3dc8348fd752c850f3e95`，上一提交为
`7450341934a8ff77bf05b90d9f708786e3eb3996`（2026-09-07）。

来源：[更新说明](https://github.com/852wa/Anime2.5DRig/blob/7ddbd9943ea3152561b3dc8348fd752c850f3e95/IMPROVEMENTS.md)、
[应用实现](https://github.com/852wa/Anime2.5DRig/blob/7ddbd9943ea3152561b3dc8348fd752c850f3e95/lib/app.js)。

与本次有关的更新包括头发延迟跟随身体倾斜、耳饰/尾巴摆动、语义别名和细长部件发束定位修复。
另有锚点编辑、独立眨眼/眉毛/微笑面捕、平滑与校准、OBS 同步、视频导出及编辑操作改进。
不能把整个双弹簧机制都算作本周新增。上游使用自己的 WebGL 变形与视频输出，
未提供可直接接入本工程的 Spine 烘焙或通用布料碰撞求解。

本次借鉴其随动方向，在现有 Spine 管线上独立实现；未执行或复制其渲染器。
上游参考文件保存在 `tmp/m5-follow-up/upstream/`，上游许可为 MIT。

## 已实现

- 发束增加可选级联惯性：下段从已求解上段的实际烘焙轨道取得驱动，固定头皮区域保持。
- 前后发之外识别 `side hair`、`hair` 和明确的中日文别名。只转换已单骨随 head 的兼容网格；
  不推断呆毛根朝向，不覆盖其他父骨或已有变形。
- 裙装、袖布继续从既有服装辅助骨取得驱动，保留袖口和身体混合边界、已有修形。
- 增加独立 `objects` 通道：对已单骨绑定的物件/挂饰建立摆动控制骨，保留原父骨、UV、三角形和贴图。
  挂点位于父骨局部包围盒，可按区域调整横纵比例；这是几何提案，不是已识别的真实缝合/挂接位置。
- 物件残余、多骨绑定、已有 deform 和附件切换均保留原结果，并显示不支持原因。
- 动作编辑页提供选择区域、强度、刚度、阻尼、摆角、挂点、撤销与草稿恢复；制作页也可开启物件通道。
- 同一个 Spine 包保存全部烘焙轨道。时间轴正拖、倒拖无需重跑物理。
- 旧配置补入关闭的物件通道和关闭的级联开关；旧接受记录、原动作和源素材不变。
  新构建配置使用 `joint-face-hair-cloth-follow-v2`，没有冒用旧候选的视觉接受。

## 使用入口

工作台「角色动作编辑」→「载入已有身体动作」→「联合动画」。
启用「发梢跟随上游发束」及需要的「裙袖响应」「挂饰与物件随动」，构建后共用时间轴播放、下载 Spine。
参数输入与实际结果分开：编辑后显示结果过期，需重新构建。

本次两份实际候选：

| 角色 | 播放 / 调参 | 范围 |
|---|---|---|
| Alice | [播放](http://127.0.0.1:8918/api/motions/motion-8eaad35a75dd4f169101aa74318fa72e/view/player.html) / [调参](http://127.0.0.1:8918/motion-editor.html?joint=motion-8eaad35a75dd4f169101aa74318fa72e) | 前后发级联、裙摆、人偶、基础表情 |
| 辉夜 | [播放](http://127.0.0.1:8918/api/motions/motion-312863cacd8d4b96b73baef7c09f588c/view/player.html) / [调参](http://127.0.0.1:8918/motion-editor.html?joint=motion-312863cacd8d4b96b73baef7c09f588c) | 前后发级联、双袖、裙摆、基础表情 |

## 验证与限制

- 108 项联合动画测试（含物件/服装开关隔离）、22 项联合任务测试、60 项制作链测试通过；27 项编辑页状态/恢复/任务测试通过。
- 内置浏览器验证：新候选参数恢复、修改后的结果过期提示、实际播放，以及从 6 秒倒拖至 2 秒。
- 两份导出包独立下载回读通过，原 PNG、编辑版骨架和主包通道一致，未影响区域误差 0。
- 两角色各 2,181 帧官方 WebGL Runtime 几何检查通过，共 4,362 帧、140 张捕获帧。
  实际 Runtime 包版本 4.3.13；该证据不等同 Spine 编辑器授权或发布。
- 两角色固定根/挂点误差 0；Core 独立顺播、倒拖同帧误差 0，顶点与 CPU 最大误差约 0.0001432 px。
- 保护机制真实缩小了响应：Alice 前后发保留 12.5%、裙摆 25%、人偶 50%；
  辉夜后发 3.125%、前发和双袖 100%、裙摆 12.5%。不把缩小后的微弱摆动描述为充分视觉验收。
- 当前候选未请求循环，强制循环仍存在首尾接续问题；原身体循环和遮挡异常保留。
- 辉夜另一较密身体来源的任务 `motion-68b0215f61d14fb58a3358ce3030a0ad` 因
  `character_reference_decoded_limit` 失败。没有放宽 256 MiB 校验数据限制；原 M5 固定来源构建成功。
  后续应为高密网格采用有界流式校验，当前可缩短来源片段。
- 此次属于平面、小幅、离线烘焙随动；不含布料自碰撞、精确表面遮挡、任意侧背视角或在线物理。
  普通刚性上衣不会仅因打开裙袖响应而自动生成衣料骨链。
- 本次新效果仍待用户阶段视觉验收；历史 M5 六份已接受结果保持原样。

复现下载及 Runtime 回读：

```powershell
$env:PYTHONPATH='src;tests;tools'
python tools/check_joint_follow_delivery.py motion-8eaad35a75dd4f169101aa74318fa72e motion-312863cacd8d4b96b73baef7c09f588c --output tmp/m5-follow-up/delivery
node tests/check_joint_delivery_runtime.mjs tmp/m5-follow-up/delivery E:/proj/unusual/localset/tmp/spine43-verification/node_modules/@esotericsoftware/spine-core
```

证据：`tmp/m5-follow-up/delivery/delivery-report.json`、`official-loop-report.json`。
