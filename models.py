from datetime import datetime
from pydantic import BaseModel


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
    origin: list[Stop]
    destination: list[Stop]
    departure: datetime
    arrival: datetime
    duration: int | None
    carriers: list[Carrier]


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
    legs: list[Leg]
    stopcount: int | None
    stops: list[Stop]


class FlightResponse(BaseModel):
    status: bool
    message: str | None
    data: list[Flight]


if __name__ == "__main__":
    with open("data/flight_response_example.json") as f:
        js = f.read()

    fr = FlightResponse.parse_raw(js)

    print(fr)

    assert fr.message is not None
