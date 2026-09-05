from typing import Literal

from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"]


class TokenPayload(BaseModel):
    # `sub` is a string on the wire (RFC 7519 4.1.2); this issuer puts a user
    # id in it. Declared int so a non-numeric subject fails validation -> 403,
    # rather than reaching a query that expects an integer -> 500.
    sub: int
