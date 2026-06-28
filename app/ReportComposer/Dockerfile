FROM --platform=linux/arm64 python:3.12-slim

WORKDIR /var/task

COPY src/ ./src/
COPY app/ReportComposer/pyproject.toml app/ReportComposer/main.py ./

RUN pip install --no-cache-dir -e . awslambdaric

ENV PYTHONPATH=/var/task/src

ENTRYPOINT ["/usr/local/bin/python", "-m", "awslambdaric"]
CMD ["main.handler"]
