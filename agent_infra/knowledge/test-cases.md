# 测试用例库（既有沉淀）

> 本文档是团队既有测试用例的索引。变更分析后按风险检索此处，判断可复用（reuse）
> 还是需要新增（generate）。用例编号 TC-0xx 全局唯一，脚本生成时以编号溯源。

## 定价模块（shop/pricing.py）

### TC-001 折扣金额四舍五入到分
- 位置: tests/test_pricing.py::test_apply_discount_rounds_to_cent
- 覆盖风险: 金额舍入口径、分单位精度
- 关键断言: apply_discount(100.0, 0.15) == 85.0；apply_discount(10.009, 0.0) == 10.01

### TC-002 阶梯折扣率边界
- 位置: tests/test_pricing.py::test_tier_discount
- 覆盖风险: 折扣档位变更（新增/调整 DISCOUNT_TIERS 档位未同步断言）、阶梯边界值
- 关键断言: tier_discount(50)==0.0；tier_discount(100)==0.05；tier_discount(600)==0.10

### TC-003 订单总价组合计算
- 位置: tests/test_pricing.py::test_total_price
- 覆盖风险: 单价×数量、阶梯折扣叠加、总价口径
- 关键断言: total_price([("apple", 2)], TABLE) == 7.0；total_price([("book", 3)], TABLE) == 128.25

## 已知无既有用例的风险面（检索到本节 = 建议新增）

- 订单均值/统计类（stats）：暂无用例沉淀，涉及异常吞吐与空集合行为时建议 generate
- 负数数量/退货单：暂无用例沉淀，涉及数量符号语义时建议 generate
- 促销折扣率上限：折扣率上限约束（0.20）在 discount-policy.md，测试侧暂无用例
