from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.claims import GRID_SIZE

# #RRGGBB. Anchored, so "#fff000; DROP" and "red" are both rejected here rather
# than reaching a browser that will cheerfully render whichever half it likes.
HEX_COLOUR = r"^#[0-9a-fA-F]{6}$"


class ClaimCreate(BaseModel):
    # No `owner`. It comes off the verified token, so the caller cannot state
    # it -- which is the difference between an identity and a nickname.
    # Half-open corners, like range(): one tile at (4, 7) is x0=4, x1=5.
    x0: int = Field(ge=0, lt=GRID_SIZE)
    y0: int = Field(ge=0, lt=GRID_SIZE)
    x1: int = Field(gt=0, le=GRID_SIZE)
    y1: int = Field(gt=0, le=GRID_SIZE)
    colour: str = Field(pattern=HEX_COLOUR)

    @model_validator(mode="after")
    def at_least_one_tile(self) -> "ClaimCreate":
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("x1 and y1 must be greater than x0 and y0")
        return self


class ClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    x0: int
    y0: int
    x1: int
    y1: int
    owner: str
    colour: str
    status: str
    expires_at: datetime
