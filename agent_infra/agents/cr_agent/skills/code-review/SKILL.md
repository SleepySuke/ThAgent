---
name: code-review
description: CR 方法论：检查清单、severity 分级标准、验证流程
---

# code-review：CR 方法论

## 检查清单（按类型）

- exception：bare except / 吞异常丢失现场 / 该抛不抛
- consistency：实现语义变化但测试未同步（跑 pytest 验证）、接口改名波及调用方
- bug：边界值（空集合/零/负数）、符号错误、静默容错改变预期行为
- maintainability：重复实现已有函数的逻辑、超长函数、缺少复用

## severity 标准

- high：错误结果或吞异常导致故障不可见（线上风险）
- mid：行为与测试/契约不一致，需要同步修正
- low：可维护性/重复代码，不阻塞合并

## 验证流程

1. 读懂 diff 后先形成怀疑列表
2. 每条怀疑用工具取证：读代码上下文或跑测试/lint
3. pytest 失败 → 检查是实现错了还是测试过期（consistency）
4. 无证据的怀疑直接丢弃
