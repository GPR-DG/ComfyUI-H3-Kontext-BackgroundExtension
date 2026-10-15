# Changelog

## Unreleased

## 1.0.0

- [新增] 独立 Kontext 背景扩展，仅补缺失能力并复用已安装的固定版本背景 Core，不重复打包原 H3/API/A2。
- [修复] 注册入口按 Python 编码声明读取相邻插件源码，避免合法非 UTF-8 插件阻断扩展加载。
