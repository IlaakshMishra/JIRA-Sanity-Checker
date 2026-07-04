FROM --platform=linux/arm64 python:3.12-slim

WORKDIR /app

COPY agentcore/estimation/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/agents/estimation_agent.py .
COPY agentcore/estimation/agent.py .

EXPOSE 8080
CMD ["uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8080"]
