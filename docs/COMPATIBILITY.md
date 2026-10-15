# 提供者选择与支持边界

## 原节点取证

HardCutRunner main `55ce7b27dde514ee79b3df7d52b78d7442f4dd38` 注册 19 个节点：

```text
H3HardCutRunner, H3HardCutRunnerShotPromptEmptyShot, H3HardCutRunnerFunControl,
H3ShotSceneVLM, H3OptionalPicture3, H3HardCutRunnerSceneVLM,
H3HardCutRunnerSceneVLMFunControl, H3CShotPlanner, H3CShotSelectPad,
H3CShotPolicy, H3CPromptCompiler, H3CShotTrim, H3COrderedMergeStep,
H3COrderedMergeFinish, H3CShotDualRefPad, H3CShotGuideWindowPlanner,
H3CShotGuideWindowSelect, H3CShotGuideWindowAppend, H3CShotReferenceRouter
```

main 没有任何本次背景类。固定 feature 增加六个 H3C 背景类，不改变上述 19 个名称。
本扩展 main 模式提供 14 个背景类，与原 19 个注册名称交集为空。
原 API/A2 main 另有 8 个名称，与本包交集也为空；原插件自行拥有其 STORE、路由和 WEB_DIRECTORY，本扩展不导入它们。

## 加载顺序

1. 已有注册背景类：验证它们来自同一实际模块，且五文件 SHA 匹配；已有类不重新注册。部分注册只从同模块补缺，绝不实例化第二套缓存。
2. 尚未注册但活动 custom_nodes 目录含固定 feature：验证五文件与固定 feature 入口的第六个哈希。保留这六个名称的注册权给原 feature；本包仅注册 H3K。H3K 在业务执行时动态查到原 Core。
3. 无背景提供者：只加载本包 background_core 五个业务模块。它们不导入旧 runner/Modular C 或外部 API。
4. 多个 Core 提供者、混合类身份、错误源码、未知 feature 入口、其他 H3K 所有者：明确阻断，注册表不改写。

目录改名的固定 feature 仍可按内容识别。`.disabled` 和 CLI custom-node whitelist 被尊重。
使用管理器策略阻止插件导入、运行时热插拔、其他 ComfyUI 分支加载器、多个未知重叠插件，不属于已验证的启动配置。
固定 feature 必须实际启用并成功加载；仅磁盘存在但被 RH 隐式拦截时不能当作兼容证明。

## 状态和清理

BackgroundTaskHandle 持有唯一 BackgroundCache / EnvironmentMatcher。H3K state 挂在该真实 task 上，不创建第二套同名任务缓存。
H3K 给该 handle 添加弱引用 cleanup 包装，原 Core cleanup 保留，finally 清空 H3K 字典和张量证据。
默认内存 SQLite 按任务隔离；显式数据库也以 task_id 隔离，cleanup 不删除其他任务的数据库文件。
SQLite 连接不允许跨线程共享；并发测试采用每工作线程独立连接，同数据库事务认领只有一个胜者。
ComfyUI 正常单 worker 串行执行图；并发入队不等于并行神经推理。

## 保持原语义

H3K 的五文件 SHA 校验原样保留，按原实现允许 CRLF/LF；没有把未知源码哈希加入白名单。
额外入口哈希只用于判断稍后是否会注册全部六类，不改变 H3K 业务来源合同。
原工作流字节、节点 ID、连线、控件和 Qwen/Z-Image 输入输出不修改。
本次完整 JSON Missing Node 检查依赖隔离主机的真实第三方插件，不把它们或伪造同名类混进发布包。
