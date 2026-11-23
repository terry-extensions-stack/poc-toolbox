FROM reg.dev.mahanova.com/registry/public/mahanova/python-uv:3.12.11-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.8.14 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-default-groups --no-editable

FROM reg.dev.mahanova.com/registry/public/mahanova/python-uv:3.12.11-slim-bookworm
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
RUN mkdir -p /tmp/podcasts && chown 10001:10001 /tmp/podcasts
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/pyproject.toml /app/pyproject.toml
COPY alembic.ini ./
COPY migrations ./migrations
USER app
EXPOSE 8000
CMD ["uvicorn", "poc_toolbox.main:app", "--host", "0.0.0.0", "--port", "8000"]
