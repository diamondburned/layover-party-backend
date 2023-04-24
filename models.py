from datetime import datetime
from pydantic import BaseModel


class AuthorizedUser:
    id: str

    def __init__(self, id: str):
        self.id = id


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


class UserResponse(BaseModel):
    id: str
    email: str
    first_name: str
    profile_picture: str | None


class MeUpdate(BaseModel):
    email: str | None
    first_name: str | None
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
    layover_hours: float | None


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
    layover_hours: float | None


class FlightApiResponse(BaseModel):
    status: bool | None
    message: str | object | None
    timestamp: int | None
    data: list[Flight] | None


class DetailStop(BaseModel):
    id: str
    name: str
    displayCode: str
    city: str


class Layover(BaseModel):
    segmentId: str
    origin: DetailStop
    destination: DetailStop
    duration: int | None


class CarrierDetail(BaseModel):
    id: str
    name: str | None
    displayCode: str | None
    displayCodeType: str | None
    brandColor: str | None
    logo: str | None
    altId: str | None


class Segment(BaseModel):
    id: str
    origin: DetailStop
    destination: DetailStop
    duration: int | None
    dayChange: int | None
    flightNumber: str | None
    departure: datetime
    arrival: datetime
    marketingCarrier: CarrierDetail | None
    operatingCarrier: CarrierDetail | None


class LegDetail(BaseModel):
    id: str | None
    origin: DetailStop | None
    destination: DetailStop | None
    departure: datetime
    arrival: datetime
    segments: list[Segment] | None
    layovers: list[Layover] | None
    duration: int | None
    stopCount: int | None


class FlightDetail(BaseModel):
    legs: list[LegDetail] | None
    pop_score: int | None


class LayoverDb(BaseModel):
    user_id: str
    arrive: datetime
    depart: datetime
    iata_code: str


class FlightDetailResponse(BaseModel):
    status: bool | None
    message: str | object | None
    timestamp: int | None
    data: FlightDetail | None


class AddOrRemoveLayoverRequest(BaseModel):
    iata: str
    depart: datetime
    arrive: datetime


class LayoversResponse(BaseModel):
    class Layover(BaseModel):
        iata: str
        airport: Airport
        arrive: datetime
        depart: datetime

    layovers: list[Layover]


class AssetUploadResponse(BaseModel):
    path: str


if __name__ == "__main__":
    with open("data/flight_response_example.json") as f:
        js = f.read()

    fr = FlightApiResponse.parse_raw(js)

    assert fr.message is not None
    assert fr.data is not None
    assert fr.data[0].legs is not None
    assert fr.data[0].legs[0].stops is not None
    assert len(fr.data[0].legs[0].stops) > 0

    with open("data/flight_detail_response_example.json") as f:
        js = f.read()

    fdr = FlightDetailResponse.parse_raw(js)

    assert fdr.data is not None
    assert fdr.data[0].legs is not None
    assert fdr.data[0].legs[0].segments is not None
    assert len(fdr.data[0].legs[0].segments) > 0
    assert fdr.data[0].legs[0].layovers is not None
    assert len(fdr.data[0].legs[0].layovers) > 0

    print("Bueno ✊🍆💦")
