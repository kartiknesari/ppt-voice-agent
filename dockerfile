# Use a Python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Set the working directory to /app
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy the lockfile and pyproject.toml first to leverage Docker cache
COPY uv.lock pyproject.toml /app/

# Install dependencies without installing the project itself
RUN uv sync --frozen --no-install-project

# Copy the rest of the application code
COPY . /app

# Install the project
RUN uv sync --frozen

# Place the virtual environment in the path
ENV PATH="/app/.venv/bin:$PATH"

# Reset the entrypoint, don't invoke `uv`
ENTRYPOINT []

# Run the application
# Replace 'main.py' with your application's entry point
CMD ["uv run python", "main.py", "start"]
