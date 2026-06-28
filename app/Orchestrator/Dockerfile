FROM --platform=linux/arm64 python:3.12-slim

RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0 \
    libffi-dev shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /var/task

COPY src/ ./src/
COPY app/Orchestrator/pyproject.toml app/Orchestrator/main.py ./

RUN pip install --no-cache-dir -e . awslambdaric

ENV PYTHONPATH=/var/task/src

ENTRYPOINT ["/usr/local/bin/python", "-m", "awslambdaric"]
CMD ["main.handler"]
