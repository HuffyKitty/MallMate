"""Alembic 运行环境：复用应用配置和 SQLAlchemy 元数据。"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# 导入 models 会把全部表注册到 Base.metadata，供 --autogenerate 比较使用。
from app import models  # noqa: F401
from app.core.config import settings
from app.db.base import Base


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ConfigParser 会把百分号当作插值符，因此连接地址中的百分号需要转义。
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """拒绝无连接的 ``--sql`` 模式。

    当前迁移需要检查目标库中已有表、列、约束和重复数据，再决定创建或接管方式。
    离线模式没有数据库连接，无法可靠作出这些判断；若勉强生成 SQL，可能得到一份
    与目标数据库实际结构不匹配的脚本。
    """

    raise RuntimeError(
        "MallMate 暂不支持 Alembic 离线 --sql：迁移必须连接目标数据库，"
        "以检查旧表结构和现有数据。请先备份数据库，再执行 "
        "`python -m alembic upgrade head`。"
    )


def run_migrations_online() -> None:
    """连接目标数据库并在事务中执行迁移。"""

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
