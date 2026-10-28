# Python 3.12 with uv already installed
FROM ghcr.io/astral-sh/uv:0.13.5-python3.12-trixie-slim

# Never run as root inside the container
RUN useradd --create-home reqlens && mkdir /app && chown reqlens /app
USER reqlens
WORKDIR /app

# No download cache in the image, it would only add size
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_CACHE=1

# Dependencies first: this layer is only rebuilt when uv.lock changes
COPY --chown=reqlens pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

# Then the app itself
COPY --chown=reqlens src ./src
COPY --chown=reqlens app.py ./
COPY --chown=reqlens .streamlit ./.streamlit
COPY --chown=reqlens docs/assets ./docs/assets
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
