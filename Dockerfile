FROM reg.dev.mahanova.com/registry/public/mahanova/python-uv:3.12.11-slim-bookworm AS builder

ARG UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV UV_HTTP_TIMEOUT=300 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_PROGRESS=1

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
        --locked \
        --no-dev \
        --no-default-groups \
        --no-install-project

COPY README.md ./
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
        --locked \
        --no-dev \
        --no-default-groups \
        --no-editable


# ============================================================
# Stage 2: Runtime
# ============================================================

FROM python:3.12.11-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PODCAST_SUBTITLE_FONT=/usr/share/fonts/truetype/harmonyos/HarmonyOS_Sans_SC_Regular.ttf

WORKDIR /app

# 1. Install runtime system dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    find /etc/apt/sources.list.d/ -type f \
        -exec sed -i 's@http://deb.debian.org@https://mirrors.tuna.tsinghua.edu.cn@g' {} + \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-noto-cjk \
    && groupadd --gid 10001 app \
    && useradd \
        --uid 10001 \
        --gid app \
        --no-create-home \
        --shell /usr/sbin/nologin \
        app \
    && install -d -m 755 -o app -g app /tmp/podcasts \
    && install -d -m 755 /usr/share/fonts/truetype/harmonyos

# 2. Copy Python virtual environment
COPY --from=builder /app/.venv /app/.venv

# 3. Copy application metadata and source
COPY --from=builder /app/pyproject.toml ./pyproject.toml
COPY --from=builder /app/src ./src

# 4. Copy database migrations
COPY alembic.ini ./
COPY migrations ./migrations

# 5. Install custom font
COPY --chmod=644 fonts/HarmonyOS_Sans_SC_Regular.ttf \
    /usr/share/fonts/truetype/harmonyos/HarmonyOS_Sans_SC_Regular.ttf

# 6. Run as non-root user
USER app

EXPOSE 8000

CMD ["uvicorn", "poc_toolbox.main:app", "--host", "0.0.0.0", "--port", "8000"]
