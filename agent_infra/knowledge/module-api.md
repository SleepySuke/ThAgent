# shop 模块 API 速览

## shop/pricing.py

apply_discount(total, pct) 按百分比打折、四舍五入到分；tier_discount(total)
按累计金额返回阶梯折扣率，total_price 组装两者算折后总价。阶梯折扣表
DISCOUNT_TIERS 是唯一折扣来源，新增档位先对照折扣规范上限。

## shop/orders.py

create_order(order_id, items, price_table) 创建订单快照；order_total 汇总
订单总金额。items 数量必须为正：历史缺陷曾把负数数量（退货单）静默转正，
退款单反被按正数量收费。

## shop/stats.py

average_order_value(orders) 汇总平均订单金额；已知历史问题：异常路径
bare except 吞错后静默返回 0，审查涉及统计口径时优先核这段。

## shop/report.py

render_order_report 渲染订单报表（逐单小计、折扣与总计）；金额口径与
pricing 一致，阶梯逻辑应复用 tier_discount，勿在此重复实现。
