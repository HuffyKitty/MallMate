FROM python:3.11-slim
WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/fixtures ./fixtures
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY knowledge /app/knowledge
RUN pip install --no-cache-dir .
EXPOSE 8000
# 容器启动时先升级数据库，再启动 API。迁移失败时容器不会带着旧表结构继续运行。
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]

