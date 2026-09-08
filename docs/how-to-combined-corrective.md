# 主关节与远端 corrective 组合诊断

新增 `autospine.combined-corrective-preview/v1`，目标 Spine 4.3.26。固定采用横向宽度实验 factor 4 的候选权重，先计算远端 corrective，再执行主关节半角混合与有界投影，最后转换为每个骨骼影响的局部 deform offset。

每个区域检查 45 个不同组合姿态，加上结尾 setup 共 46 个 key；主关节为 −30/0/30/60/90°，远端为 −90/−60/−30/−15/0/15/30/60/90°。每 0.5 秒使用 stepped key 切换，总长 22.5 秒。没有验证连续插值。

## 生成与复验

在仓库根目录设置 `PYTHONPATH=src`，执行：

```powershell
python -m autospine_workbench.benchmark.combined_corrective_cli `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --atlas ../tmp/r2b-isolation/alice-v1.json `
  --width ../tmp/r2b-distal/alice-width-v1.json `
  --directory ../tmp/r2b-combined/alice `
  --output ../tmp/r2b-combined/alice-v1.json `
  --zip ../tmp/r2b-combined/alice-v1.zip
```

将 alice 换为 lingxian 或 crino 可生成另两个角色。CLI 精确重建 atlas 与 width 的来源链，要求它们引用同一 mesh/skeleton。`source_original_atlas_sha256` 保存原 atlas 地址；`source_atlas_sha256` 表示仅替换候选权重后的派生 atlas 身份，由 reader 重算，不冒充已发布源 atlas。`read_combined` 重建整个输出并核对内容地址；ZIP 和逐文件摘要独立校验。

官方播放使用既有 `tools/verify-ownership-runtime.mjs`，首个参数改为 `../tmp/r2b-combined` 的绝对路径；依赖安装及 Editor 导入方式见[原播放说明](how-to-ownership-spine43.md)。Runtime 为官方 npm 4.3.13，JSON 目标为 Editor 4.3.26，两者版本分别记录。

## 本次结果

|区域|失败姿态数 / 46|最小面积比|状态|
|---|---:|---:|---|
|Alice 左／右腿|0 / 0|0.550 / 0.550|候选待复核|
|铃仙左／右腿|0 / 5|0.550 / 0.492|左侧候选、右侧阻塞|
|琪露诺左／右手臂（layer-004）|10 / 10|0.367 / 0.458|阻塞|
|琪露诺左／右腿（layer-005）|0 / 0|0.550 / 0.550|候选待复核|

面积比仍要求 0.5–2，边长拉伸不超过 2；检查翻转、有限数、固定顶点及局部 offset 重建。`distal_stage_passed` 单独保留；区域状态由最终组合几何判定，不用中间阶段结果代替最终检查。

官方 Runtime 检查每角色 91 帧，包括所有 key 和保持区间中点，三角色共 273 帧通过。最大运动顶点误差 0.000108 px，隔离纹理参考对照最大通道差 1/255。旧 raw LBS 路径另回归 363 帧通过。播放通过说明目标数据与采样正确，不代表上述阻塞区域变形合格。

全部输出保留 `authority:none`、`production_authorized:false`。未采用残余、权重或新绑定；动态跨层接缝、完整角色、连续动作尚未通过。下一步优先建立连续动作 bake 的固定步长 QA，并检测腿与鞋、前臂与手的动态接缝；三处失败保持显式阻塞，不放宽阈值。
