FROM python:3.14-slim-bookworm@sha256:9ab8d9c8514b44f90cf0029dd42fdd7e9e211e639c8b995304cc04568dee900f AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/recebimentos/process_extrato:/app/recebimentos/process_extrato/btg:/app/recebimentos/process_extrato/mdb \
    HOME=/home/muv
WORKDIR /app
COPY requirements.txt requirements-container.txt ./
RUN python -m pip install --no-cache-dir -r requirements-container.txt \
    && groupadd --gid 10001 muv \
    && useradd --uid 10001 --gid muv --create-home muv \
    && mkdir -p /data/months /data/templates /data/config /data/technical \
    && chown -R muv:muv /data
COPY recebimentos/process_extrato/ ./recebimentos/process_extrato/
USER 10001:10001
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=15s --start-period=30s --retries=3 \
    CMD ["python", "-m", "container_runtime", "health"]
CMD ["python", "-m", "container_runtime", "start"]

# Explicit test target; pytest does not enter the default runtime image.
FROM runtime AS test
USER root
COPY requirements-dev.txt pyproject.toml ./
RUN python -m pip install --no-cache-dir -r requirements-dev.txt
USER 10001:10001
HEALTHCHECK NONE
CMD ["python", "-m", "pytest", "-p", "no:cacheprovider"]

FROM runtime AS app
