# 最小依赖与源码调用证据

业务来源：Core `e1516896fb2b90e66b9d3ae811a5004cb5ff5626`，H3K `687c052fb2d5cb618a763c5ab8cc672df1295d1b`。
8 个运行时文件按 Git blob/SHA256 保持原字节；完整表在 UPSTREAM-MANIFEST.json。
本包新增的只有入口、提供者选择与交付文档/测试，没有重写业务算法。

## 动态调用链（不是按文件名猜测）

```text
H3K.nodes.core()
  -> nodes.NODE_CLASS_MAPPINGS['H3CBackgroundResolve']
  -> importlib.import_module(真实类.__module__)
  -> 校验同目录五个 Core 文件（归一化 CRLF）
H3KBackgroundResolve.run()
  -> state(真实 BackgroundTaskHandle)
  -> task.cache.resolve(candidate, FilteredMatcher, revision)
  -> BackgroundCache.resolve(): SQLite BEGIN IMMEDIATE / receipt / index
  -> task.matcher.match_for_production()
  -> BackgroundCache.apply(): PENDING 或真实历史 READY
H3KBackgroundWashClaim.run()
  -> task.cache.claim_wash()：事务 INSERT OR IGNORE，一个认领 token
H3KBackgroundSource / StageGuard / PromptCapture / StagePreview
  -> 同一个 task._h3k 的 recipe、canvas、token 与阶段证据
H3KBackgroundFinish.run()
  -> 校验 Kontext + Qwen + Z-Image 原尺寸/像素/归属证据
  -> task.cache.attach_clean(..., wash_token=...)
  -> READY，输出 A/B/clean 与原提示词接口
H3CBackgroundTaskCleanup.run()
  -> task.cleanup() -> Core cache.cleanup() + H3K cleanup_task_state()
```

重要区别：H3K 使用注册类定位真实 Core 模块，但并非直接调用 `H3CBackgroundResolve.run()`；H3K 自己按 recipe 过滤视图，再调用同一 BackgroundCache。这正是原始实现，不应改成错误的节点转发。

## 五个 Core 模块为什么必须保留

| 文件 | 实际被调用的职责 |
|---|---|
| h3_background_nodes.py | BackgroundTaskHandle、六节点、IMAGE/MASK 转换；H3K core() 动态定位点 |
| h3_background_cache.py | BackgroundCache：任务范围 SQLite、resolve/claim/attach/release/cleanup |
| h3_background_contracts.py | CandidateBackgroundRecord、BackgroundView、EnvironmentDecision 和输入合同 |
| h3_best_background_frame.py | select_best_frame：原始帧质量、遮挡、光流打分与原尺寸候选 |
| h3_environment_matcher.py | EnvironmentMatcher：SIFT、几何/视角、dense veto 与 production_request_key |

导入闭包仅包含标准库、NumPy、OpenCV、Torch。Kontext 画布读取官方 `comfy_extras.nodes_flux.PREFERRED_KONTEXT_RESOLUTIONS`，不捆绑模型或复制 ComfyUI。
H3KRecipe 通过 ComfyUI registry / folder_paths 获取实际下游类源码及模型元信息，所以它会感知下游处理配方改变。
没有对 API/A2 的 Python import、STORE、账本、供应商系统、管理路由或 WEB_DIRECTORY 依赖；这些从 Production 全部排除。

## 测试替身与未覆盖事项

免费执行测试只替换 Kontext 神经采样、Qwen 推理、Z-Image 推理和最终视频推理消费者；真实 BackgroundCache、matcher、节点、官方 lazy 调度、PreviewImage 均未替换。
Kontext 替身要求 steps=6，但这不等于验证真实六步模型去人物质量。
原完整 JSON：全部后端节点类型在真实第三方注册表中可用；H3C/H3K 的端口与真实实现逐项比对；全部 JSON 连线做序列化一致性检查。
其他第三方动态端口没有逐个执行实现级校验，真实前端导入和完整模型推理也未在本轮验证。
RH 云端安装权限、实际 Core 源码、模型文件、Qwen/Z-Image/GPU 兼容性和视觉质量需 RH 技术实机验证。
