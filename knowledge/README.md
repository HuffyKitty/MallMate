# MallMate 演示知识库

本目录保存 Agent 可检索的 Markdown 业务知识。当前版本由项目根据公开法规和常见电商售后流程生成，用于开发、演示和离线评估，并非某家真实平台的正式承诺。

## 数据约定

- 每篇文档必须有 `id`、`title`、`version`、`category`、`status` 元数据。
- `id` 一经进入评测集便保持稳定；正文修订时提高 `version`。
- 法律规定与项目演示规则分开表述。发生冲突时，以适用法律和真实平台已公示规则为准。
- 当前 Markdown 会在启动种子阶段写入 PostgreSQL。后续 PDF、Word 和表格经过解析、切片后进入同一知识导入流程。

## 当前覆盖

无理由退货、质量问题、换货、不适用退货商品、物流查询、物流异常、破损、少件错发、退款到账、凭证、人工转接、优惠与发票、隐私、售后流程和安全事件。

## 主要法规参考

- [中华人民共和国消费者权益保护法](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/fgs/art/2023/art_0a323e046fba43f0b6e9e977f1e8d5fc.html)
- [网络购买商品七日无理由退货暂行办法](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/fgs/art/2023/art_26ca8fe29e184edd899fa0a7a060d935.html)
- [中华人民共和国电子商务法](https://www.samr.gov.cn/zfjcj/tzgg/art/2023/art_d337c3291e8b40459ca03dea54395856.html)
- [中华人民共和国消费者权益保护法实施条例](https://app.www.gov.cn/govdata/gov/202403/19/513111/article.html)
