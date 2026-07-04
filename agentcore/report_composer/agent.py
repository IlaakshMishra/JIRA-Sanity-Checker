from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from report_composer import compose

app = FastAPI()


class InvocationRequest(BaseModel):
    input: dict[str, Any]


@app.post("/invocations")
async def invoke(request: InvocationRequest):
    report_markdown = compose(
        request.input["findings"], request.input["sprint_name"]
    )
    return {"output": {"report_markdown": report_markdown}}


@app.get("/ping")
async def ping():
    return {"status": "healthy"}
