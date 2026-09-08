# 分区纹理页的 Spine 4.3.26 诊断播放

本入口把ownership隔离纹理页接入独立的Spine诊断Adapter。
它允许查看未批准区域的编码和纹理采样，不修改正式Adapter的生产准入规则。
残余不绑定、不显示；其它角色图层也不在这个子集包内。

```powershell
python -m autospine_workbench.benchmark.ownership_target_cli --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. --atlas ../tmp/r2b-isolation/alice-v1.json --directory ../tmp/r2b-spine-ownership/alice --output ../tmp/r2b-spine-ownership/alice-v1.json --zip ../tmp/r2b-spine-ownership/alice-v1.zip
```

## 包内容与坐标

- 根目录`skeleton.json`、`skeleton.atlas`及`textures/`供Runtime加载，共用隔离纹理页。
- `editor/skeleton.json`与`editor/images/`供Editor导入，逐附件图片由对应纹理区域裁出，避免MISSING。
- 整页UV先按region矩形反算为附件局部UV，再由Runtime映射回整页；往返误差门槛1e-9。
- 骨骼局部y、角度与逐骨局部顶点y反号，将PSD y-down映射到Spine y-up。
- `distal-inspection`是2秒、远端±30°的原始LBS检查动作，没有采用此前宽度策略或corrective。
- 源网格QA与pending复核状态逐项保留，残余列为`excluded_unbound`，完整角色仍blocked。

纹理页的透明隔离边不会由Spine Editor的逐附件图片自动复现；本次Editor仅提供正确图片路径，
未自动操作Editor完成导入验收。已完成的实际播放检查来自官方WebGL Runtime。

## 官方Runtime验证

此次按用户明确的播放验证请求，在临时依赖目录使用官方
[`@esotericsoftware/spine-webgl` 4.3.13](https://www.npmjs.com/package/@esotericsoftware/spine-webgl/v/4.3.13)。
Runtime patch与Editor数据版本4.3.26分开记录。第三方文件不加入仓库核心依赖，也不装进导出ZIP。

```powershell
node tools/verify-ownership-runtime.mjs ../tmp/r2b-spine-ownership ../tmp/spine43-verification "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

外部依赖目录需要固定的官方Runtime4.3.13与playwright-core；工具检查版本并记录实际Runtime字节摘要。
设置`KEEP_PREVIEW=1`会在全部验证成功后保留仅监听127.0.0.1的播放服务，终端输出实际URL。
服务只读取文件白名单；可用`?character=alice`、`lingxian`、`crino`切换角色。

使用官方SkeletonJson、TextureAtlas、AnimationState和WebGL renderer，按4.3的setupPose/appliedPose API执行。
每角色从0到2秒以60Hz检查121个时刻：

1. Runtime整页UV与版本中立工件比较，误差≤1e-6。
2. setup和逐时刻顶点与独立FK/LBS计算比较，误差≤0.001px。
3. 同一骨架分别使用共享页和独立遮罩纹理，后者增加相同2px透明边，以相同采样语义作对照。
4. 渲染像素逐通道比较，绝对误差≤1/255；画面非空、实际发生运动、无页面错误或非有限顶点。
5. 每帧顶点位于预览视口范围内；保存setup与弯曲截图。

最初直接拿clamp边缘的独立图片对照时出现像素差异；加入合同要求的透明边后对照通过。
这不是放宽像素门槛，两个纹理路径必须先具有一致的边界采样定义。

## 本次结果与限制

三个角色全部通过，共363个固定时刻。最大UV误差约2.90×10⁻⁸，
最大setup误差约6.11×10⁻⁵px，最大动画顶点误差约9.95×10⁻⁵px，最大颜色通道差1/255。
24项针对性Python测试、三个实际Schema/ZIP检查及Alice完整来源回放通过。完整测试套件未运行。
验证运行于Chrome/SwiftShader，不等于覆盖所有GPU或Spine Editor版本。

导出回执的`runtime_status=not_evaluated`保持不可变，之后运行的证据独立记录，不能重写旧导出身份。
证据见[真实验证记录](benchmark/ownership-spine43-2026-09-08.json)，包含导出、Runtime、测试脚本和截图摘要。
现有三骨网格仍可能翻转或拉伸；这次通过只证明编码、时间线、采样与参考一致，未证明动作美术质量。
下一步应在此真实播放入口接入经验证的corrective与主关节组合测试，然后处理跨分区接缝和完整角色组合。
