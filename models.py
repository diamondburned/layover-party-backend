from datetime import datetime
from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    id: str
    token: str
    expiry: int
    first_name: str
    profile_picture: str | None


class RegisterRequest(BaseModel):
    email: str
    password: str
    first_name: str


class MeResponse(BaseModel):
    id: str
    email: str
    first_name: str
    profile_picture: str | None


class Airport(BaseModel):
    iata: str
    name: str
    city: str
    state: str | None
    country: str
    lat: float
    long: float


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
    entity_id: int | None
    alt_id: str | None
    parent_id: int | None
    parent_entity_id: int | None
    name: str | None
    type: str | None
    display_code: str | None


class Leg(BaseModel):
    id: str | None
    origin: Stop | None
    destination: Stop | None
    departure: datetime
    arrival: datetime
    duration: int | None
    carriers: list[Carrier] | None
    stops: list[Stop] | None
    layover_score: float | None


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
    layover_score: float | None


class FlightResponse(BaseModel):
    status: bool | None
    message: str | object | None
    timestamp: int | None
    data: list[Flight] | None


if __name__ == "__main__":
    with open("data/flight_response_example.json") as f:
        js = f.read()

    fr = FlightResponse.parse_raw(js)

    assert fr.message is not None
    assert fr.data is not None
    assert fr.data[0].legs is not None
    assert fr.data[0].legs[0].stops is not None
    assert len(fr.data[0].legs[0].stops) > 0

    print("Bueno ✊🍆💦")
