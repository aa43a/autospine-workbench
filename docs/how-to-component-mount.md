# 同一图层的多个部件分别绑定

一个源图层可同时包含头部与背部饰件。`component_mount` 使用全部非零 alpha 的四邻接连通域，
分别为主要部件提出父骨骼候选；小组件合并为单独残余，绝不默默删除或塞入最近骨骼。
父骨骼距离只是几何建议，最终映射可由确切来源绑定的人工决定指定。

生成器在原 slot 所处位置插入部件，保留原图层顺序和原 PNG；所有可见 RGBA 像素只归属一次。
每个新部件使用父骨骼局部坐标的单骨加权四边形，不修改原骨架或新增拍翼轨道。
已有附件的逐帧顶点保持原值，全部动画重新通过几何检查与官方 Runtime 验证。
不支持的贴图映射、原有 deform/附件切换/动态 draw order、未知父骨骼或失效决定都会阻塞。

开发入口：

```powershell
python tools/build-character-component-mount.py --state-root workspace --source <确切整角色候选> --slot <静态区域> --parent head --parent chest --decision <来源绑定的决定.json> --output <输出目录>
```

生成的 `component-mount.json` 记录像素覆盖、分区、父骨骼及是否已确认；`component-mount-decision.json`
保留实际决定。省略决定时只生成未确认候选。官方捕获器遇到该候选会附加可拖动的捕获帧时间轴。
目前生成入口仍为 CLI，后续需要接入工作台当前项目编排、保存与撤销，不能宣称当前项目已采用该包。

小恶魔本次四片翼已按用户确认分别随 head/chest，371 个零散像素单独保留。
这项确认不包括拍翼运动、补画隐藏部件、删除残余或整角色视觉验收。

本次 1,675 帧官方 WebGL 4.3.13 验证通过，setup 无新增或缺失可见像素，首帧截图与分区前逐字节一致。
证据见 [小恶魔四翼整角色候选](benchmark/xiaoemo-component-mount-v1.json)。
