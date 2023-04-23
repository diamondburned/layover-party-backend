from models import Flight, FlightDetailResponse
from db import db


def set_popularity_for_flights(flights: list[FlightDetailResponse]):
    for flight in flights:
        assert flight.data is not None
        flight.data.pop_score = 0

    iatas = []
    iata_flights = [[] for i in range(len(flights))]
    for i in range(len(flights)):
        flight = flights[i]
        if flight is None or flight.data is None or flight.data.legs is None:
            continue

        for leg in flight.data.legs:
            if leg is None or leg.layovers is None:
                continue

            for layover in leg.layovers:
                iatas.append(layover.destination.displayCode)
                iata_flights[i].append(layover.destination.displayCode)

    cur = db.cursor()
    res = cur.execute(
        f"""
            SELECT iata_code, COUNT(*) FROM layovers
            WHERE iata_code IN ( {', '.join(['?']*len(iatas))} )
            GROUP BY iata_code
        """,
        iatas,
    )

    rows = res.fetchall()
    if rows is None:
        return

    # convert rows into a dict
    popularity = {}
    for row in rows:
        popularity[row[0]] = row[1]

    for i in range(len(flights)):
        flight = flights[i]
        assert flight.data is not None

        for iata in iata_flights[i]:
            if iata in popularity:
                flight.data.pop_score += popularity[iata]
