---
id: policy_after_sales_process
title: 售后申请、审核与状态说明
version: mallmate-demo-2026.10-v1
category: after_sales
status: active
---
# 售后申请、审核与状态说明

标准流程为：识别问题、补齐订单和原因、核验订单归属、读取适用政策、资格预览、用户确认、创建申请、审核、寄回或补发、退款或结案。

## 状态含义

- `pending_evidence`：等待用户补充必要凭证。
- `pending_review`：资料已提交，等待规则或人工审核。
- `approved`：申请已通过，等待下一操作。
- `waiting_return`：等待用户寄回商品。
- `refund_processing`：已发起退款，等待支付渠道处理。
- `completed`：本次售后已完成。
- `rejected`：申请未通过，必须保存原因和适用规则。
- `cancelled`：申请已被用户或系统依法取消。

创建售后单属于写操作。系统必须先展示预览并取得明确确认，使用幂等键防止重复创建；网络超时时先查询原请求结果，再决定是否重试。状态变化应写入历史和审计事件，不能只覆盖当前值。
