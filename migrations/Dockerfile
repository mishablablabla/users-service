# Console app that applies DB migrations (alembic upgrade head). Used as a Kubernetes Job.
# Build from the repository root:  docker build -f migrations/Dockerfile -t users-migrations .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt alembic==1.14.0
COPY api/app ./app
COPY migrations ./migrations
WORKDIR /app/migrations
RUN useradd --create-home --uid 10001 appuser
USER appuser
CMD ["alembic", "-c", "alembic.ini", "upgrade", "head"]
