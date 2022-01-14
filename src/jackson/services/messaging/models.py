from pydantic import BaseModel


class InitResponse(BaseModel):
    inputs: int
    outputs: int
