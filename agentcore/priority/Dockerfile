FROM --platform=linux/arm64 python:3.12-slim

WORKDIR /app

COPY agentcore/priority/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/agents/priority_agent.py .
COPY agentcore/priority/agent.py .

EXPOSE 8080
CMD ["uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8080"]
