# 膝部生成材质：局部阴影减弱，接缝与形状仍失败

2026-09-24。使用内置 image_gen 编辑原 layer-004 腿部纹理，生成独立姿态材质，没有使用 CLI/API fallback。原始资产和历史采用记录不变。

原图 211×699，输出 725×2170，均为带透明度的 RGBA PNG。输出比例变化，不能通过现有同画布素材回交合同。为检查其局部效果，新增独立 normalized-UV affine 配准实验模块，不修改生产回交校验，不赋予自动采用权限。恒等归一化 UV 是明确的未验证假设，不能视为图像已准确对齐。

仅替换上一版左膝两块表面中，UV 纵坐标质心位于 0.32–0.51 的 76／87 个三角形。原/新材质互斥显示；几何、权重、deform、骨骼动画保持。原素材用于其余三角形。九个诊断时刻均核对原槽位顶点保持不变；新增纹理不改变原 PNG 字节。该实验仍继承父候选的九姿态范围与未解决的重叠外形，不宣称完整时间轴修复。

候选 c7836638a56e799d222af75dc6954aff3392712ff760819e0522317daca9b482。官方 Core 4.3.13 正反向 18 次核验通过，最大顶点误差 0.000151431px。官方 WebGL 九帧、32 槽位数值通过，误差 0.000154236px，目标 Spine 4.3.26。

实际查看 0 与 0.9 秒捕获：尖锐膝部阴影减弱；替换区域边界形成可见色阶接缝，原有端部突起和错误外形仍在。不能以补图或数值成功替代外观验收。候选不采用，不继续重复相同提示词抽图。

后续需要将材质配准、边界衔接和姿态外形一起验证；单纯同 UV 换图、仅消除阴影不能完成 M4 大动作。现有工作台同画布回交仍保持严格尺寸约束。

新增两项测试及原四项区域材质测试通过，覆盖仅替换区域 UV 改变、原材质/几何保持、反射/退化/越界映射拒绝，以及互斥材质切换。

生成图保存于 localset/tmp/m4-motion-center/knee-material-v1/generated-knee.png，SHA256 为 72e089116d6440d29a4459e871d98f3afc23e3dfe3c766644e232f79d1a44bd0。候选与数值参考同目录。新捕获包 b70b08a83ec6071f04945c2cf5c5ca34921bfe6f971f502ad57c71143acce829 位于 knee-material-render-v1；runtime/frames 保存九帧。v2 补充源纹理摘要与实际尺寸读取，候选字节保持一致，复用相同捕获证据。

## 使用的完整生成提示词

Use case: precise-object-edit. Asset: experimental alternate knee texture for a 2D skeletal animation, not a new character drawing. Edit the provided isolated leg texture. Preserve its exact portrait canvas aspect ratio, position and scale of the leg, thigh top, calf, white sock and foot, original anime painting style, colors, and genuinely transparent background. Change only the knee transition in the middle-upper part of the image, approximately normalized y=0.32 to 0.51. In that small zone remove the dark exterior contour stroke and the pointed dark knee crease; replace them with softly painted pale peach skin with subtle shading matching the adjacent thigh/calf. Extend this skin smoothly a small distance beyond the old knee outline on both sides only within that zone, tapering the extension back to the untouched leg contour at the ends. This is an underlap texture for overlapping animation surfaces: no black seam or hard outline is wanted within that knee transition. Everything outside that local zone must remain unchanged, especially sock, foot, upper thigh, pose, and positioning. No extra limbs, objects, labels, checkerboard or opaque background. Return one transparent PNG texture with the same composition and aspect ratio.
