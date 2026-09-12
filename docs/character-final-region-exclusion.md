# 修复后残余排除

用户确认的六处残余共 986 个 alpha 1–7 像素，来源及纹理摘要见
`benchmark/character-residual-confirmation-v1.json`。

排除在动作合成、纹理转移及裙装变形之后执行。不会把辉夜已经转入有效附件的边缘像素
按旧残余整块删除。每个决定都先对同一确切候选检查图层、静态区域与纹理摘要，再整体应用。
任何来源变化或重复区域都会拒绝；原始候选和 PNG 保留，可以回到未排除版本。

工作台入口：整角色候选 → 最终残余排除。勾选已检查的静态残余并保存后，重新构建整角色候选。
当前保存采用追加历史与版本冲突检查，页面提供撤销。保存时保留确切动作、纹理修复、裙装选项，
后续重建复用这些选项；更换组合前先撤销最终排除。来源不匹配时明确阻塞，不能自动迁移确认。
前置排除与最终排除使用独立历史；没有最终排除的旧请求与产物身份保持不变。

命令行入口：

```powershell
python tools/apply-final-region-exclusions.py --state-root workspace --confirmation docs/benchmark/character-residual-confirmation-v1.json --character xiaoemo --output ../tmp/character-final-exclusion-v1/xiaoemo
```

对应辉夜使用 `--character huiye`。输出 `generation.json` 包含新旧内容地址和确认文件摘要。
旧运行报告不作为新候选的证据；新候选需要单独官方 Runtime 验证。
排除确认只影响所选静态残余，不确认剩余加权附件或整角色视觉质量。新候选仍会列出相应待办。

小恶魔、辉夜已通过工作台重建，输出与离线排除包内容地址一致；分别完成 1,675 / 2,062 帧
官方 WebGL 4.3.13 验证（目标 Spine 4.3.26），采样网格检查通过。重启后通过接口核对决定与候选恢复。
确切任务、产物及报告摘要见 [工作台验证记录](benchmark/character-final-workbench-v1.json)。
此前的确认文件保持原字节；其待应用状态是历史快照，本记录表示当前实际应用结果。
