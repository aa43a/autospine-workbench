# 将已选手臂Mesh接入组合包

使用同一历史绑定草稿重放手臂Bake和目标附件，合入既有刚性层／腿鞋包。
两侧forearm骨轨道与calf/foot轨道分离，合并前验证同骨架、同片长、无冲突轨道及无附件重名。
原包全部附件在121个时刻的世界坐标必须逐值不变，否则拒绝输出。

```powershell
python -m autospine_workbench.benchmark.integrated_limbs_cli `
  --state-root workspace --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --base ../tmp/r2b-mixed-character/alice/1d1ba1e7d499f12a3f5a536600b7ea9ebebd4ecba68243f25486623b20cd506f.json `
  --donor ../tmp/r2b-mesh/alice-character-v1.json `
  --output-dir ../tmp/r2b-integrated-limbs/alice
```

分区归属使用内容寻址ownership atlas，不通过名称前缀猜测。source order仍未复核。
新增手臂纹理使用2px透明padding，原附件不改权重、不改deform；新包有独立JSON、Atlas、PNG、
Editor图像路径、确定性ZIP、内容寻址报告与`read_integrated`重算入口。

本切片已验证：11附件几何通过，官方4.3.13 Runtime（导出目标4.3.26）121帧通过。
最大setup误差0.0000611px、运动误差0.0000903px、UV误差2.97e-8，画布溢出0；
共享Atlas／独立纹理每通道差异≤1。13项针对性测试通过，未跑全量测试。
官方Runtime命令与混合包相同，将root替换为 `../tmp/r2b-integrated-limbs`，末尾指定alice。

## 剩余复核

review.html列出14个包缺项，并链接到binding-review.html全量复核页。
复核页复用已有 `complete-layer-bindings` 命令，以历史alice-defaults-confirmed草稿为输入：
保留7个bind记录，其余保持pending，新增头部选项不自动选中。
页面保留23层完整记录；16个整层pending包括腿／鞋两层，其分区已进入动画，
但独立分区候选不能覆盖或伪造整层绑定决定。因此“包缺14层”和“整层pending16层”不是矛盾。

生成全量页时使用前述命令的manifest/workspace，并运行：
`python -m autospine_workbench.benchmark complete-layer-bindings`
配合 `--draft ../tmp/r2b-multibone/alice-defaults-confirmed.json`、
`--html ../tmp/r2b-integrated-limbs/alice/binding-review.html`、
`--draft-output ../tmp/r2b-integrated-limbs/alice/binding-review-draft.json`、
`--output ../tmp/r2b-integrated-limbs/alice/binding-options.json`。

浏览器检查了14条缺项、全量23条记录和默认16条待处理筛选，历史records逐字典不变。
当前包仍缺眼口、裙子等部件及570残余像素，肩部／躯干接触未获得新QA。
下一步消费用户复核后的决定，再补完整组合与接缝测试；不把可播放视为生产通过。
