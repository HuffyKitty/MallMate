"""手动写入本地演示数据的命令入口。

用法（在 backend 目录执行）：

    python -m app.bootstrap.seed_cli

业务应用启动时也可以通过 ``MALLMATE_SEED_DEMO_DATA=true`` 调用同一套
``seed_demo`` 逻辑。单独保留这个入口，是为了让 Docker 初始化、故障恢复和
开发者手动补数据时都有一个明确、可重复执行的命令。
"""

from app.bootstrap.seed import seed_demo
from app.core.config import settings
from app.core.enums import Environment
from app.db.session import SessionLocal


def main() -> None:
    """创建短生命周期数据库会话并幂等补齐演示数据。"""

    # 演示数据包含固定开发密码的客服和管理员账号。即使操作人员误执行了
    # 这个模块，生产环境也必须在连接数据库前直接拒绝。
    if settings.environment == Environment.PRODUCTION:
        raise RuntimeError("生产环境禁止写入 MallMate 演示数据")
    if not settings.seed_demo_data:
        raise RuntimeError(
            "当前配置已关闭演示数据；如需本地初始化，请设置 "
            "MALLMATE_SEED_DEMO_DATA=true"
        )

    # SessionLocal 的上下文管理器负责在命令结束时关闭数据库连接。
    # seed_demo 内部完成事务提交；发生异常时让进程以非零状态退出，方便
    # PowerShell、Docker 或 CI 正确识别初始化失败。
    with SessionLocal() as db:
        seed_demo(db)

    print("MallMate 演示数据初始化完成。")


if __name__ == "__main__":
    main()
