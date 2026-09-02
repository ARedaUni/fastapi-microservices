from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.claims import GRID_SIZE

# #RRGGBB. Anchored, so "#fff000; DROP" and "red" are both rejected here rather
# than reaching a browser that will cheerfully render whichever half it likes.
HEX_COLOUR = r"^#[0-9a-fA-F]{6}$"


class ClaimCreate(BaseModel):
    x: int = Field(ge=0, lt=GRID_SIZE)
    y: int = Field(ge=0, lt=GRID_SIZE)
    owner: str = Field(min_length=1, max_length=40)
    colour: str = Field(pattern=HEX_COLOUR)


class ClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    x: int
    y: int
    owner: str
    colour: str
    status: str
    expires_at: datetime
