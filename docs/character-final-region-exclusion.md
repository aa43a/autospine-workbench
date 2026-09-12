# 修复后残余排除

用户确认的六处残余共 986 个 alpha 1–7 像素，来源及纹理摘要见
`benchmark/character-residual-confirmation-v1.json`。

排除在动作合成、纹理转移及裙装变形之后执行。不会把辉夜已经转入有效附件的边缘像素
按旧残余整块删除。每个决定都先对同一确切候选检查图层、静态区域与纹理摘要，再整体应用。
任何来源变化或重复区域都会拒绝；原始候选和 PNG 保留，可以回到未排除版本。

当前入口：

```powershell
python tools/apply-final-region-exclusions.py --state-root workspace --confirmation docs/benchmark/character-residual-confirmation-v1.json --character xiaoemo --output ../tmp/character-final-exclusion-v1/xiaoemo
```

对应辉夜使用 `--character huiye`。输出 `generation.json` 包含新旧内容地址和确认文件摘要。
旧运行报告不作为新候选的证据；新候选需要单独官方 Runtime 验证。
目前还未接入工作台的持久化最终阶段选择，不能宣称当前工作台待办已自动清除。
后续接入必须保留前置排除与最终排除的阶段区别、撤销及输入变化阻塞。
