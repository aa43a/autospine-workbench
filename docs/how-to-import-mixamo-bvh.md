# 将本地 Mixamo 行走素材接入 MotionIR

该入口准备动作候选，不自动绑定角色，不自动锁脚，也不推断循环。
需要 Blender 的 FBX/BVH 插件，以及已安装的工作台 Python 环境。

1. 用 `tools/export-fbx-bvh.py` 在 Blender 后台导出，参数为源 FBX、输出 BVH，
   加 `--root-only` 适配现有 MotionIR 根平移规范。
2. 用 `tools/verify-fbx-bvh.py BVH INSPECTION_JSON REPORT_JSON` 核对导出。
   对应 inspection 文件由导出工具产生。所有帧与关节必须通过；若非根平移被省略后不再一致，
   停止使用这个转换结果，不通过放宽误差强行导入。
3. 调用 `tools/prepare-mixamo-motion.py`，明确声明投影与源单位参考长度。例如对已验证的
   Y 向上、Z 向前、厘米单位素材：

```powershell
python tools/prepare-mixamo-motion.py --bvh walking-root.bvh --map-output map.json --state-root workspace --clip-id walk.source.sagittal --reference-length 81 --screen-x +Z --screen-y +Y --depth +X
```

参考长度是根位移归一化的源单位尺度，必须按实际素材设置；81仅为当前样本的显式取值。
带 `mixamorig:` 命名空间的文件可使用 `--prefix mixamorig:`。缺少关节或父子关系不符会报错。
输出复用既有 MotionIR 编译器、内容寻址 store 和回读验证，不改变旧算法身份。

默认不生成接触注释。需要时，传入 `--contact-parameters contact.json`，明确提供五个值：

```json
{"floor":0,"height":3,"speed":10,"minimum_frames":3,"gap_frames":0}
```

floor/height为源长度单位，speed为源长度单位每秒。以上厘米阈值仅用于当前样本的候选分析，
不是经过独立标注校准的普适精度保证。检测使用左右ToeBase，并保留`annotation_only`。

当前映射提供12个身体骨段和根位移轨道，省略髋侧偏移、锁骨和头部独立旋转。
侧向投影的行走不能直接证明正面角色可用：后续仍需目标姿态映射、脚滑、缩短、出平面、
服装和官方Runtime验证。循环保持false，不能把首尾有根位移的素材直接当作原地循环。
