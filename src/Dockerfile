# syntax=docker/dockerfile:1

FROM python:3.13.9-slim-bookworm

WORKDIR /code

COPY . .

# Upgrade pip to fix security vulnerability GHSA-4xh5-x5gv-qwph
RUN pip install --no-cache-dir --upgrade pip>=25.3

RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Install Node.js and pnpm with specific versions
RUN apt-get update \
    && apt-get install -y curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g pnpm@10.6.0 \
    && node --version \
    && pnpm --version

# Build React frontend
WORKDIR /code/frontend
RUN pnpm install --frozen-lockfile=false \
    && pnpm build \
    && rm -rf node_modules \
    && rm -rf /root/.local/share/pnpm \
    && rm -rf /root/.pnpm-store

# Return to backend directory
WORKDIR /code

# Clean up unnecessary packages
RUN apt-get purge -y nodejs curl \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 50505

CMD ["gunicorn", "api.main:create_app", \
     "--bind", "0.0.0.0:50505", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--timeout", "120"]