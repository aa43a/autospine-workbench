# FBX 转换环境持久化

2026-09-24 检查当前工作台发现 blender_available=false。已安装 E:/soft/blender/blender.exe，但此前服务重载遗漏 AUTOSPINE_BLENDER 环境变量，导致新 FBX 不可转换。Kimodo 生成环境仍 configured，BVH 与 NPZ 导入不受该问题影响。

新增服务端状态目录 config/motion-tools.json，字段 blender_executable 为绝对文件路径。优先级为显式环境变量、持久化配置、PATH。无效显式配置不静默回退。文件只由服务端管理，HTTP 上传不接受程序路径；总览仅公开配置来源与状态，不公开路径。当前机器已写入状态目录配置，不提交机器路径到版本库。工作台显示配置来源及缺失/无效原因。

九项配置与导入测试通过，覆盖重建管理器后持久化配置保留、环境变量优先、错误配置不回退、相对路径拒绝以及既有导入取消/失败合同。

真实重新导入 breathing_idle.fbx，源 SHA 67bf8b91cb77fec8873bb059cddcb96198c9ca348a16cfa6eb60171dabbd5370，新任务 motion-2671c6fdbc10444592420e6f8f4ad838 succeeded。Blender 实际执行转换；299 帧、53 关节核对通过，最大 world error 5.132562750494726e-7（源坐标单位），最大时间误差 1.7763568394002505e-15 秒。MotionIR bundle 9a1840b148f2a635f8046e1005c759bdf706cb5448b5d08d3537cec350217d8c 与既有内容一致并复用。

证据 tmp/fbx-config-live-v1；此项只修复导入能力，不代表新增整角色 Runtime 或视觉验收。三角色八动作的原始技术失败继续保留。
