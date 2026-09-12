# 袖装子帧材料约束试验

2026-09-12。候选 9872c5c5b9d319993e1445a7a1a4653cb69323814640a30bfb06c2c200e89cb5。

新增可选 material-subframes：在准确 Spine 四分之一子帧上约束主拉伸，继续固定原有手、袖口及非布料顶点。未更改人工归属或工作台当前输出。历史 profile 保留。

- 固定边界诊断：前版 1029 个时刻、每时刻 14 条固定边没有材料反例；这只是必要条件，不证明整体可解。
- 新候选原 1029 个检查时刻：几何和材料通过，主拉伸范围约 0.712366–1.383490，最大方向比约 1.929171。
- 独立 1029 个中点检查：几何和材料通过，见 character-cloth-subframe-material-midpoints-v1.json。
- 官方 spine-webgl 4.3.13：1029 帧、25 附件，最大坐标误差 0.000197608 px。原报告位于 ../tmp/cloth-subframe-material-runtime/report.json。
- 直接检查捕获帧 wave-left-256.png：宽袖仍向上拱起，因此视觉未通过，候选未采用。这不是自然下垂或连续时间安全的证明。

材料范围 0.7–1.4 仍是探索参数，未跨角色校准。12 项针对性测试和文件长度检查通过。

复现（PYTHONPATH=src）：

```text
python tools/build-character-cloth-wave.py --state-root workspace --wave c69947dcd79fd874a73f35a236d642f088e069837ccd7a57480e9c499e621b36 --helper cloth-layer-003-component-0000 --samples 65 --exact-temporal --continuation --material --material-subframes
```

## 整角色后续工作

用户确认的 9 层绑定已记录并重建，三角色仍有 17 个整层未闭合项：8 个静态层没有候选，9 个已有加权区域但整层或残余尚未闭合。
下一切片补充版本化 topwear-front/back 刚性胸部候选，只提供待复核选项。bottomwear 保持裙/裤/衣摆歧义；小恶魔混装翼层需要区域归属，不能整层强绑。袖装自然垂落另行修正，不以数值通过替代视觉验收。
