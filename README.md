# H3 Kontext BackgroundExtension

RunningHub / ComfyUI 独立背景扩展。保留已有 H3HardCutRunner、Modular C、API 和 A2，只补背景能力；不包含旧执行器、API/A2 实现、管理前端、路由、供应商配置或工作流。

## 安装（给 RunningHub 中国大陆站技术人员）

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/GPR-DG/ComfyUI-H3-Kontext-BackgroundExtension.git
# 先复用镜像中已存在的依赖；使用 ComfyUI 实际运行的 Python
python -c "import numpy, torch, cv2; assert hasattr(cv2, 'SIFT_create')"
```

仅依赖缺失时，按 RH 镜像规范使用该 Python 安装 `requirements.txt`。已有正常 cv2 时不要叠加安装第二种 OpenCV wheel，也不要无理由升级原镜像的 Torch/NumPy。
完整重启 ComfyUI，再导入原 Kontext JSON。无需修改 JSON 或移除原 `ComfyUI-H3HardCutRunner`。
默认分支为 `main`，仓库根目录即插件入口。

## 共存范围

| 原 Core | 本扩展注册 | 原 Core 是否覆盖 |
|---|---:|---|
| `main`，`55ce7b27dde514ee79b3df7d52b78d7442f4dd38` | 6 H3C + 8 H3K | 否，原 19 个类保留 |
| background feature，`e1516896fb2b90e66b9d3ae811a5004cb5ff5626` | 仅 8 H3K，复用原 6 H3C | 否，两种加载顺序均检查 |

已测原 API/A2：Adapter `main`，`5137af844600695fd803dd5627887d4e29013941`。API/A2 独立安装，不在本包重复打包。

**不要并装另一份 H3K 提供者**，包括旧 Production 整包、Kontext BackgroundBridge，或包含 `h3_kontext_bridge` 的 Adapter feature。它们不是上述 API/A2 main。
如果已有这些重复整包，应由 RH 确认停用重复包；不要移除原 HardCutRunner。
检测到未知背景来源、多份提供者或不匹配的 SHA 时，本扩展明确拒绝加载，不静默覆盖或绕过校验。

## 节点

截图任务清单对应的 11 个精确名称：

```text
H3CBackgroundTaskStart
H3CBestBackgroundFrame
H3CBackgroundTaskCleanup
H3KBackgroundResolve
H3KBackgroundWashClaim
H3KBackgroundFinish
H3KBackgroundSource
H3KStageGuard
H3KRecipe
H3KPromptCapture
H3KStagePreview
```

另有三个真实内部 Core 能力：`H3CBackgroundResolve`、`H3CBackgroundWashClaim`、`H3CBackgroundAttachClean`。
旧 Core main 缺少时由本包补齐；固定 feature 已有时复用同一模块/类/任务状态，不重复注册。
不提供错误的 `H3StageGuard` / `H3StagePreview` 别名，也不把 AttachClean 冒充另一种 Finish 接口。

## 运行与验证边界

Python ≥ 3.10；已测 Python 3.12、ComfyUI 0.39.0 官方 CPU 调度器。已有 Qwen、Kontext、Z-Image、H3、Easy-Use 等原工作流插件和模型仍需保留。
业务源码使用固定提交原始字节，保留任务隔离、READY/PENDING、并发认领、缓存、两阶段证据和来源校验。
READY 仅证明技术流水线完成，不证明去人物视觉质量。

正常结束由原 `H3CBackgroundTaskCleanup` 清理；取消失败任务须由持有该任务的调用方显式 `task.cleanup()`。
ComfyUI 失败不会执行下游成功清理节点。没有新增强制回收、隐藏自动重试或清理管理路由；新 TaskStart 始终创建新任务。

```bash
python -m unittest discover -s tests -v
```

本地官方调度测试使用明确的 CPU 神经计算替身；没有付费 API 或真实 GPU 生成验收。
未附 Missing Node 截图、RH 实际版本/安装清单和云端运行结果，不能声称已完成截图逐字核验或 RH 云端验收。

详细证据：[兼容性](docs/COMPATIBILITY.md)、[依赖调用链](docs/DEPENDENCIES.md)、[来源清单](UPSTREAM-MANIFEST.json)、[测试摘要](verification/TEST-RESULTS.json)。
