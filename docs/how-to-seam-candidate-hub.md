# 统一查看保守候选

更新：Alice右侧已有[独立边界补充证据](how-to-seam-boundary-probes.md)，当前配置位于
`../tmp/r2b-right-boundary/hub-config.json`。该配置的页面显示183个独立目标及透明度下降复核状态；
下文旧配置仍保留原疑似点报告中的未评估状态，不将两类样本混合。

启动只读集合服务后，在同一个页面切换 Alice／琪露诺、播放动画、拖动时间轴、
下载 Spine 4.3.26 JSON／Atlas／PNG 预览包，并查看当前关系覆盖。
用户无需填写 SHA；技术身份折叠显示。此入口仅包含已有候选区域，不是完整角色。

## 启动

从仓库目录运行，配置由开发者整理一次；本机现有配置位于 `../tmp/r2b-candidate-hub/config.json`。

```powershell
$env:PYTHONPATH=(Resolve-Path ./src).Path
python -m autospine_workbench.benchmark.seam_candidate_hub_cli `
  --config ../tmp/r2b-candidate-hub/config.json `
  --runtime ../tmp/spine43-verification/node_modules/@esotericsoftware/spine-webgl/dist/iife/spine-webgl.js `
  --receipt ../tmp/r2b-candidate-hub/server.json
```

终端和 receipt 返回本机入口 URL。可指定 `--port`，默认使用系统分配的空闲端口。
服务仅绑定127.0.0.1；停止后重新运行即可恢复同一配置，不修改任何采用决定。
Runtime需外部已有的官方4.3.13文件，其SHA必须与已有捕获报告一致；不下载或随包分发。

配置是本地启动参数，不是新资产合同：`characters`数组每项包含 `character`、`direct`、
`runtime`、`candidate`、`manifest`、`admission`。后五项分别指向已有直接alpha报告、
Runtime报告、整段回退候选、预览manifest及逐关系报告；相对路径以配置目录为基准。
不根据mtime或latest猜测候选。当前支持alice、crino、lingxian，角色不可重复。

启动时重放逐关系reader，校验候选／manifest身份、全部包文件和Runtime截图SHA。
只将验证后的字节装入内存白名单；ZIP从这些字节确定性重建，不信任目录中的可变ZIP。
普通路由不暴露配置、本地路径或任意文件系统读取；不存在的文件返回404。
启动失败返回 `candidate_collection_invalid`，不会降级到未验证包。

## 当前覆盖

Alice左侧原轨道回退、右侧保留有界增量；琪露诺双侧原轨道回退。
Alice右侧仍为 `not_evaluated`，0个目标样本绝不显示通过。
其他关系仅为已有采样无新增透明度退化，原有空白仍在。
播放器中的“接缝诊断”是旧顶点邻近proxy，和上方真实alpha边界增距是不同指标。

2026-09-08：14项针对性Python测试及代码长度门禁通过；Chrome官方Runtime集成检查
完成两个角色各121帧（242帧），检查角色切换、滑块、UV／几何误差、共享／隔离采样、
ZIP下载SHA、私有配置404及页面截图。没有重跑完整测试集。
这次没有新增局部framebuffer目标，不能把242帧回归解释为Alice右侧局部接缝已验收。

下一步应独立定义Alice右侧代表性接缝采样（不能冒充“新增裂缝”点），再补原有空白、
颜色／重叠与完整角色覆盖。当前入口不改变PipelineRun、生产导出或任何自动采用规则。
