from models import Flight, FlightDetailResponse
from db import db


def calculate_popularity(
    flights: list[FlightDetailResponse],
) -> list[FlightDetailResponse]:
    iatas = []
    iata_flights: dict[str, list[FlightDetailResponse]] = {}
    for flight in flights:
        if flight is None or flight.data is None or flight.data.legs is None:
            continue

        for leg in flight.data.legs:
            if leg is None or leg.layovers is None:
                continue

            for layover in leg.layovers:
                iatas.append(layover.destination.displayCode)
                if iata_flights[layover.destination.displayCode] is None:
                    iata_flights[layover.destination.displayCode] = [flight]

                iata_flights[layover.destination.displayCode].append(flight)

    cur = db.cursor()
    res = cur.execute(
        "SELECT iata_code, COUNT(*) from layovers WHERE iata_code in ? GROUP BY iata_code",
        (iatas,),
    )

    for flight in flights:
        assert flight.data is not None
        flight.data.pop_score = 0

    rows = res.fetchall()
    if rows is None:
        return flights

    # convert rows into a dict
    popularity = {}
    for row in rows:
        popularity[row[0]] = row[1]

    for iata, flights in iata_flights.items():
        for flight in flights:
            assert flight.data is not None
            flight.data.pop_score += popularity[iata]

    return flights
