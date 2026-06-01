from pydantic import BaseModel, Field


class XuiClientPayload(BaseModel):
    email: str
    totalGB: int = Field(description="Traffic limit in bytes despite field name")
    expiryTime: int = 0
    enable: bool = True
    limitIp: int = 0
    subId: str = ""
    flow: str = ""
    group: str = ""
    id: str = ""


class ClientCreateRequest(BaseModel):
    client: XuiClientPayload
    inboundIds: list[int]


class XuiResponse(BaseModel):
    success: bool = False
    msg: str = ""
    obj: object | None = None
