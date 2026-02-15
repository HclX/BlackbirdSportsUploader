# Use a slim Python 3.11 base image
FROM python:3.11-slim-bookworm

# Install system dependencies
# bluez is required for BLE support
RUN apt-get update && apt-get install -y --no-install-recommends \
    bluez \
    lsb-release \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files first to leverage caching
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
# Sync effectively installs the project dependencies
RUN uv sync --frozen --no-install-project

# Copy the rest of the application
COPY . .

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

# Entrypoint using uv run (or directly python if deps are installed in system/venv)
# Since we used uv sync, it creates a .venv. We can run directly from it.
CMD ["python", "main.py", "--help"]
