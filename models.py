from datetime import datetime
from pydantic import BaseModel
from airports import Airport

class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    id: str
    token: str
    expiry: int


class RegisterRequest(BaseModel):
    email: str
    password: str
    first_name: str


class MeResponse(BaseModel):
    id: str
    email: str
    first_name: str
    profile_picture: str | None


class ListAirportsResponse(BaseModel):
    airports: list[Airport]


class Carrier(BaseModel):
    id: int | None
    name: str | None
    altid: str | None
    displaycode: str | None
    displaycodetype: str | None
    alliance: int | None


class Stop(BaseModel):
    id: int | None
    entityid: int | None
    altid: str | None
    parentid: int | None
    parententityid: int | None
    name: str | None
    type: str | None
    displaycode: str | None


class Leg(BaseModel):
    id: str | None
    origin: Stop | None
    destination: Stop | None
    departure: datetime
    arrival: datetime
    duration: int | None
    carriers: list[Carrier] | None


class Price(BaseModel):
    amount: float | None
    updatestatus: str | None
    lastupdated: datetime | None
    quoteage: int | None
    score: float | None
    transfertype: str | None


class Flight(BaseModel):
    id: str | None
    price: Price
    amount: float | None
    updatestatus: str | None
    lastupdated: datetime | None
    quoteage: int | None
    score: float | None
    transfertype: str | None
    legs: list[Leg] | None
    stopcount: int | None
    stops: list[Stop] | None


class FlightResponse(BaseModel):
    status: bool | None
    message: str | object | None
    timestamp: int | None
    data: list[Flight] | None


if __name__ == "__main__":
    with open("data/flight_response_example.json") as f:
        js = f.read()

    fr = FlightResponse.parse_raw(js)

    print(fr)

    assert fr.message is not None
