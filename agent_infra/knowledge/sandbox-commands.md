# 沙箱命令白名单与测试规范

## 命令白名单

CR 节点沙箱允许：python、pytest、ruff、pip、ls、cat、grep、git。
Testing 节点允许：python、pytest、ls、cat、grep。白名单之外的命令会被
policy 拒绝并记录 policy_deny 事件，不要反复尝试。

## 测试执行

跑测试统一用 python -m pytest -q（在仓库根目录）；静态检查用 ruff check .。
测试失败输出必须完整附在测试报告 artifact 里，禁止只贴结论不贴证据。
