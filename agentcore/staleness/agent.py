from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from staleness_agent import run

app = FastAPI()


class InvocationRequest(BaseModel):
    input: dict[str, Any]


@app.post("/invocations")
async def invoke(request: InvocationRequest):
    findings = run(request.input["issues"])
    return {"output": {"findings": findings}}


@app.get("/ping")
async def ping():
    return {"status": "healthy"}
