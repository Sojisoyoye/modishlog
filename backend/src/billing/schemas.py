from typing import Literal

from pydantic import BaseModel


class CheckoutRequest(BaseModel):
    tier: Literal["basic", "pro"]


class CheckoutResponse(BaseModel):
    authorization_url: str
    access_code: str
    reference: str
