# 六处剩余区域：当前内容与下一步

以 first-ten-workflow-v7 的当前候选重新读取内容寻址包，生成 `tmp/character-six-remaining-review/index.html`。只剩六个静态参考区域：五处含 alpha≥8 的内容、一处空纹理，无仅低透明度区域。

| 角色 | 区域 | 检查结果 | 下一步 |
| --- | --- | --- | --- |
| 铃仙 | layer-018 | 独立睫毛，位置在眼部 | 已生成 rigid:head 来源绑定方案，待确认 |
| 爱丽丝 | layer-022 | 发箍，位置在头顶 | 已生成 rigid:head 来源绑定方案，待确认 |
| 爱丽丝 | layer-008 | 腰侧人偶 | 待明确跟随位置；不能根据 objects 名字直接自动绑定 |
| 芙兰 | layer-000 | 翼层 | 保留此前翼部候选方向，尚未采用 |
| 芙兰 | layer-023 | 全透明头饰源图 | 修复空层可见性传递，不能仅改验收数字 |
| 幽幽子 | layer-004-unbound-residual | 袖部残余，有一个 alpha≥8 像素 | 保留，不在此前十二处授权范围 |

头部两层方案位于 `tmp/character-final-head-review/{lingxian,alice}/index.html`，包含原图、角色内位置、目标骨骼及来源摘要。已检查生成的上下文图；没有写入新绑定决定。

## 空层原因

芙兰当前语义候选 layer-023 的 `observed` 为 `empty: true, visible: false, alpha_nonzero: 0`；实际 123×77 PNG 的 alpha bbox 为 null。源图 SHA256 为 `036fd4f6c681eff3b355d614f80efba2e53fcb0a5aa65e992db0de43a8f126d1`。

`targets/spine43/workbench_preview.py` 和 `automation/character_coverage.py` 读取顶层 empty/visible，未读取上述 observed 标记。这解释了该源层仍被输出并进入待办。下一实现需同时处理编译可见性和覆盖账本，显式区分 observed 隐藏与用户覆盖；旧编译输出和内容地址必须保留，不能原地改写既有候选，也不能只放宽验收门禁。

只读来源复核结果保存在 `tmp/character-six-remaining-review/empty-source.json`。本轮未删除空图、未扩展十二处排除授权，未增加整角色完成数量。

## 可见性修复

新动画预览记录 `observed-source-visibility-v1`。编译时规范化观察值，显式顶层 empty/visible 优先；隐藏/空层不进入网格输出、静态上下文或图片导出。覆盖账本按相同版本解释来源和分区，空层标为 not_visible。无此标记的旧清单继续采用原解释，旧工件不改写。引擎内容身份包含该实现，新预览不会复用旧运行身份。

真实芙兰来源的纯编译验证中，layer-023 输出区域为空、不导出其图片，账本为 not_visible；输入语义候选摘要保持不变，setup 最大误差约 1.27e-13 px。验证记录位于 `tmp/character-six-remaining-review/visibility-verification.json`，未运行新的官方 Runtime，也未替换已有整角色候选。已有来源绑定的排除和采用仍须经过原校验，不能静默迁移到新编译结果。

回归覆盖显式覆盖优先、非法标记拒绝、隐藏加权层同时从文档/图片/账本移除，以及无版本旧清单仍按旧规则解释。

## 引擎升级后的历史读取

历史下载原先把保存的运行身份与当前引擎重新计算的身份比较，导致引擎变动后无法读取完整的旧工件。现将读取与执行分开：读取验证保存的引擎摘要和运行内容身份、封存记录、checkpoint、文件库存、scope 以及当前注册来源；执行和续跑继续要求当前引擎身份。不会根据旧摘要执行旧代码，也不会允许已变更来源的旧记录冒充 current。

真实芙兰旧运行 `run-7193a0bb91253d1798d117418e91e6c397a05ae07eb0f9d172c50df915890873` 的 91 个文件已通过全包与单文件读取验证，保存的运行字节不变；严格执行校验仍拒绝旧引擎。具体摘要见 [历史读取证据](historical-preview-read-v1.json)。测试另覆盖引擎摘要篡改、项目来源变化、文件篡改，以及新构建使用不同运行身份。

## 整角色重建差异与动作边界

独立重建基础角色（未切换工作台选择）得到 `d726eb24ecb431a9106660b6e2443a0ed2f53c3bc446f1fc5822f1551b0cf9e7`。与动作选择所绑定的旧基础 `79fa6e0a63f673828dcedd6bc49a0707a0eaba41a9f77d3ed226a8b8184e6605` 比较：骨骼、已有动画、全部保留 attachment 相同；slot 从 29 降为 28，仅移除 layer-023，同时移除该层三份导出 PNG。图集、数值参考、编辑器和运行时 skeleton、清单均发生变化。可复查结果位于 `tmp/character-visibility-upgrade/flandre/motion-blocker.json`。

动作合并返回 `character_motion_source_changed`，符合旧重放规则只允许 base receipt 变化的限制。未放宽规则、未继承 Runtime 通过状态，未覆盖此前三处残余排除和五层骨骼确认。下一切片应从原动作输入重建新来源候选，再验证排除区域内容是否未变，最后重新运行 Runtime；不能只改旧动作的 source hash。此新基础仍不是整角色验收完成包。

## 新来源动作重建与残余复核范围校验

已从原内置 idle、wave（开启局部修正）和原 BVH MotionIR 重建三动作。walk 保留 513 个采样、投影长度、有界 v2 面积修正和 ankle-proxy root 参数；重新合并后接回 reviewed-chest-v1 裙腰候选。动作集合已登记为新可选项，原选择未替换。

新增 `region_revalidation`，并接入整角色最终残余排除：新旧包不同但来源（除基础编译地址）、骨骼、完整源层行、区域 slot/attachment、原贴图和各动作逐帧区域位置全部不变时，可按原人工范围重新校验。旧决定先按旧包验证，新派生决定保留完整 original_decision，并明确 new_human_confirmation=false。来源改变、内容改变、动作依赖、重复范围及已撤销决定仍阻塞；不改写人工历史。此能力不沿用绑定或整角色视觉验收。

芙兰三处残余均通过，新候选为 `b20ff271e37db859f0d1409dcb34f1c820f76e5bf013983e533002c528cf9483`。官方 WebGL Runtime 4.3.13 对 Spine 4.3.26 候选验证 1,675 帧、25 个附件，最大误差 0.000098471 px，通过当前数值与非空画面检查。详细地址与报告摘要见 [重建证据](flandre-visibility-rebuild-v1.json)。复核页为 `tmp/character-visibility-upgrade/flandre/runtime/index.html`。

已查看实际捕获：腿裙遮挡仍待处理，翼层仍未采用。contact_status 仍为 not_evaluated；本次不增加十角色完成数量，不声称整角色视觉通过。下一步在新来源上完成这些部件，再切换工作台候选和重新核对绑定范围。
