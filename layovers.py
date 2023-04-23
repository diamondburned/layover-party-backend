from datetime import date as Date

from models import Flight, FlightDetailResponse, LayoverDb, UserResponse
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
            WHERE iata_code IN ( {', '.join(['?'] * len(iatas))} )
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


def get_users_in_layover(user_id: str, iata_code: str):
    cur = db.cursor()
    res = cur.execute(
        """
            SELECT * FROM layovers
            WHERE iata_code = ?
            AND user_id = ?
        """,
        (iata_code, user_id),
    )

    row = res.fetchone()
    if row is None:
        return []

    curr_user = LayoverDb(**row)

    other_res = cur.execute(
        """
            SELECT arrive, depart, users.* FROM layovers
            JOIN users ON layovers.user_id = users.id
            WHERE iata_code = ? AND user_id != ?
            AND arrive <= ? OR depart >= ?
            GROUP BY user_id
        """,
        (iata_code, user_id, curr_user.depart, curr_user.arrive),
    )

    rows = other_res.fetchall()
    if rows is None:
        return []

    users = [UserResponse(**r) for r in rows if r[0] != user_id]

    times = {}
    for row in rows:
        times[row[2]] = (row[0], row[1])

    matching = []

    for user in users:
        # if other departs after you arrive
        if times[user.id][1] > curr_user.arrive and times[user.id][1] - curr_user.arrive >= 30:
            matching.append(user)
        # if other arrives before you depart
        elif times[user.id][0] < curr_user.depart and curr_user.depart - times[user.id][0] >= 30:
            matching.append(user)

    return matching


if __name__ == "__main__":
    # other 7055876208000499712
    users = get_users_in_layover("7055837737219260416", "LAX")

    assert users is not None
    assert len(users) > 0

    print("Bueno ✊🍆💦")
