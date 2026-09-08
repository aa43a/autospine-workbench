# 已选刚性绑定与四肢候选同包

此切片将历史确认草稿中的5个刚性层，与当前4个腿鞋分区组成同一Spine 4.3.26包。
刚性图层使用单骨、权重1的四边形Mesh，等价表达其刚性变换，复用现有加权附件Runtime探针。
不会给待确认层新增选择，也不继承任何生产授权。

```powershell
python -m autospine_workbench.benchmark.mixed_character_cli `
  --state-root workspace --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --atlas ../tmp/r2b-isolation/alice-v1.json `
  --candidate ../tmp/r2b-stable-fallback/alice/ffeba51258fee821bbd111a34f50e9e60023d7adb789cea16581cd655894b617.json `
  --draft ../tmp/r2b-multibone/alice-defaults-confirmed.json `
  --output-dir ../tmp/r2b-mixed-character/alice
```

输出JSON／Atlas／PNG、Editor图片路径版本、确定性ZIP、内容寻址报告及review.html缺项页。
复核页不进入Runtime文件身份或ZIP。CLI重放绑定草稿、候选选项、图像和ownership来源；
同骨架setup必须一致，刚性四角必须重建到原bbox。`read_mixed`可重算报告。
原四肢attachments、动画轨道及纹理保持不变；新刚性纹理页有2px透明padding并独立命名。
slot按源层顺序插入，未产生Draw Order批准；新增刚性层不继承腿鞋alpha接缝证据。

## 官方Runtime验证

现有验证工具增加可选单角色参数，省略时仍跑原三个角色：

```powershell
node tools/verify-ownership-runtime.mjs ../tmp/r2b-mixed-character `
  ../tmp/spine43-verification "C:/Program Files/Google/Chrome/Application/chrome.exe" alice
```

可设置KEEP_PREVIEW=1在验证通过后保留本机预览服务。官方Runtime版本为4.3.13，
由既有外部依赖提供，不随输出分发；导出目标为4.3.26。

Alice 9个附件的121帧验证通过：UV误差≤2.915e-8、setup误差≤0.000062px、
运动误差≤0.000091px、画布溢出0、共享／独立纹理每通道差异≤1。
12项针对性测试及代码长度门禁通过。未跑全量测试。

接入的刚性层为layer-000、006、007、013、021；16层仍缺失，570残余像素仍排除。
其中2个已选手臂Mesh尚未接入当前分区包，其余14层仍pending。
因此当前预览没有完整眼口、裙子、手臂等部件是明确缺项，不是图片加载成功就算整角色完成。

下一步应优先整合已选手臂Mesh，准备眼口、裙子等待决定层的集中复核入口。
每次组合变更后重新跑同包Runtime，继续保留原接缝复核状态；不以9个附件可播放代替完整角色验收。
