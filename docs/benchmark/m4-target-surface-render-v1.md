# 原贴图三维表面渲染：未通过

2026-09-24。使用原 PNG 和 UV，对 target-surface-dq-full-v1 的 0、0.9 秒进行 LBS/DQ 同相机、同尺度渲染。Blender Cycles CPU、8 samples、Linear 过滤、Standard 色彩、无去噪。输出真实 RGBA 图像，没有编辑源纹理。

结果：`localset/tmp/m4-motion-center/target-surface-render-v2/index.html`。四张 640×800 图像均核对 SHA、尺寸、RGBA 与非空透明范围；已查看站立 DQ 和蹲下 LBS/DQ。初次运行使用相对 render.filepath，Blender 解析到 C:/tmp 后导致预期产物找不到；v1 失败保留，工具已改用绝对路径。

蹲下图像仍有膝部尖折与明显透明缺口；DQ 改变局部曲线但未带来可接受外观。站立时原绘制的膝部明暗线仍在。此处是固定髋的双腿隔离实验，没有身体、裙摆、鞋附件和地面；无法验收整角色接缝、脚接触。双面显示的都是同一正面图，不能冒充有效背面材料。

表面 SHA：294bd58da732d036e8563a08825ea95133da632301b64595b064e22b954bfb6a。
姿态 SHA：720be7e08ca1bfd656722604ac406d437d3e5ea8a16d7067793c17b179e21eb0。
0.9 秒 DQ 图 SHA：96bf97e5c5f55fe6fe4d280fc46c8a610dae1f234e2999885e6820abe1f4dc09。

结论：浅深度表面加三维 DQ 不足以解决原图的大幅屈膝，保持未采用。不能凭 27→4、14→1 的几何数字提升为通过。下一步需要区分原 alpha/UV 支持不足和表面自身折叠，再决定关节表面或补充姿态材质；不扩大深度参数或删除失败三角形。M4 的实际角色表达、官方 Runtime 验收仍未完成。
