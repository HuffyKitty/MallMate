# MallMate 数据库迁移

Alembic 从 `app.core.config.Settings.database_url` 读取数据库地址，因此本地开发、Docker
和生产环境使用同一套迁移代码，不在迁移文件中保存账号或密码。

在 `backend` 目录执行：

```powershell
python -m alembic upgrade head
```

创建后续迁移：

```powershell
python -m alembic revision --autogenerate -m "变更说明"
```

首个迁移处理两种情况：

1. 空数据库：创建 MallMate 当前完整表结构。
2. 已由旧版 `Base.metadata.create_all()` 建好的数据库：仅当每张已有业务表都包含受支持
   基线的必需列时，才保留业务表和数据，并补充认证表、`customers.user_account_id` 及
   Alembic 版本记录。

该接管逻辑不是任意旧版本升级器。已有表若缺少基线列，迁移会列出具体表和字段后停止；
需要先备份数据库，再为该旧版本编写专用迁移。第二个迁移还会再次核对完整基线，以保护
已经用早期 `0001` 文件登记过版本的数据库。

`order_items` 从 `20261014_0002` 起要求 `(order_id, product_id)` 组合唯一。同一订单、
同一商品应使用一行并通过 `quantity` 表达数量；历史重复行不会被自动合并，迁移会明确
报出第一组冲突，待人工核对数据后再继续。

当前迁移依赖实时检查数据库结构和数据，因此不支持 `alembic ... --sql` 离线生成脚本。
请连接目标数据库执行 `python -m alembic upgrade head`。

为了保护第二种数据库，首个迁移的 `downgrade()` 只移除认证结构，不删除已有业务表。
生产环境执行迁移前仍应先备份数据库。
