# 翼根选择与胸骨跟随预览

本切片提供可撤销根部选择和两级SVG刚性运动，不是Spine Runtime或生产绑定。
默认所有组件未选择；不会代替用户选择根部、确认层序或批准遮挡。

## 操作

打开 ../tmp/r2b-wing-review/crino/review-v2.html。
C0–C3各有两个候选；选择后红点显示根部。胸骨滑杆驱动上衣和所有翼片，
局部滑杆只驱动已选组件；未选组件只跟随胸骨。角度范围均为±15度。
可撤销选择、恢复JSON草稿、回到setup、下载完整草稿。
前后顺序开关仅用于试验，不进入草稿或层序决定。

草稿始终包含32条组件记录；28个无根部的小组件保留root_index=null。
草稿合同autospine.wing-root-draft/v1绑定精确roots内容地址；未知根部、缺记录、
组件重排、错误来源、授权字段变化均拒绝。下载是选择草稿，不是生产批准。

## CLI和重放

仓库目录设置PYTHONPATH=src后执行：
```powershell
python -m autospine_workbench.benchmark.wing_root_review_cli --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. --roots ../tmp/r2b-wing-roots/crino/roots.json --html ../tmp/r2b-wing-review/crino/review-v2.html --draft-output ../tmp/r2b-wing-review/crino/draft.json
```

添加 --draft <已保存草稿> 可以恢复；更新输出请使用新html及draft-output路径，避免覆盖旧版本。
read_draft经roots地址重放完整源闭包后校验草稿。
JSON Schema位于schemas/wing-root-draft-v1.schema.json。
首版交互只允许一个挂接关系，多个关系明确拒绝，不隐式混用根部或胸骨。

## 像素与几何边界

4个主要组件按原alpha>=8像素拆成互不重叠的预览纹理；低alpha边缘及微小组件放入独立残余层。
重建时逐像素检查alpha及所有非透明RGB完全一致。原source和原候选不改变。
局部摆动时残余层只跟随胸骨，因此边缘可能不连续；尚未生成边缘归属和生产Mesh权重。
上衣源层还覆盖翼片投影，局部运动截图会有重影。该问题不能用改变根部或隐藏残余掩盖。
上衣作为整层绕胸骨刚性转动也只是预览简化，不代表完整服装变形。

变换顺序为翼片绕选定根部局部旋转，再整体绕胸骨参考点旋转，使用画布Y向下坐标。
浏览器验证组合旋转时选定支点与胸骨父变换结果相同；源码纯函数测试setup和90度数值参考。
12项针对性测试通过；浏览器检查32条记录、4个可选组件、撤销、完整下载、恢复、错误来源拒绝、层序试验和支点误差。
交付草稿仍全未选，浏览器测试选择未发布。没有新的官方Runtime测试或生产动画。

浏览器回归：
```powershell
node tools/check-wing-review.mjs ../tmp/r2b-wing-review/crino ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe' review-v2.html
```

后续已接入用户草稿的 Spine 局部诊断导出，见 [翼根 Spine 预览](how-to-wing-spine-preview.md)。源层重叠与残余边缘归属仍待处理。
