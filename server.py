"""
server.py -- CS 436 Project: Simple Uber App (UDP server)
Fall 2026, CS 436

Run first, in its own terminal:
    python3 server.py

The server keeps three lists:
    customers     -- A, B, C   (username == password == name)
    drivers       -- D, E, F   (username == password == name, cars pre-registered)
    ride requests -- created as customers request rides, id starts at 1

Zones are a 3x3 grid:
    1 2 3
    4 5 6
    7 8 9
The distance between two zones is the straight-line distance between the
zone centers, rounded to 1 decimal (this reproduces Table 1 in the project
description exactly: 1->2 = 1, 1->5 = 1.4, 1->3 = 2, 1->6 = 2.2, 1->9 = 2.8).
Cost = distance * $5.

IMPORTANT: whenever the server receives or sends a message it prints a
message on the screen saying what it is doing (worth 10 points).
"""

import json
import math
import socket
from datetime import datetime

SERVER_PORT = 12000
BUFFER_SIZE = 65535          # large enough for one small headshot file

# ---------------------------------------------------------------- data ---

CUSTOMERS = {
    "A": {"username": "A", "password": "A", "name": "A",
          "zone": None, "riding": 0, "headshot": None, "addr": None},
    "B": {"username": "B", "password": "B", "name": "B",
          "zone": None, "riding": 0, "headshot": None, "addr": None},
    "C": {"username": "C", "password": "C", "name": "C",
          "zone": None, "riding": 0, "headshot": None, "addr": None},
}

DRIVERS = {
    "D": {"username": "D", "password": "D", "name": "D", "zone": None,
          "car_model": "Ford",  "car_color": "Black", "plate": "111",
          "available": 0, "headshot": None, "addr": None},
    "E": {"username": "E", "password": "E", "name": "E", "zone": None,
          "car_model": "Mazda", "car_color": "Red",   "plate": "222",
          "available": 0, "headshot": None, "addr": None},
    "F": {"username": "F", "password": "F", "name": "F", "zone": None,
          "car_model": "Tesla", "car_color": "White", "plate": "333",
          "available": 0, "headshot": None, "addr": None},
}

RIDES = []                   # list of ride-request dicts
NEXT_RIDE_ID = 1

STATUS_TEXT = {
    1: "1-requested",
    2: "2-accepted",
    3: "3-picked up",
    4: "4-dropped off",
}


# ------------------------------------------------------------- helpers ---

def now_str():
    """Current time as a readable string for the ride records."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def zone_position(zone):
    """(row, col) of a zone number on the 3x3 grid (zones 1..9)."""
    z = zone - 1
    return z // 3, z % 3


def zone_distance(zone1, zone2):
    """Straight-line distance in miles between two zones, 1 decimal."""
    r1, c1 = zone_position(zone1)
    r2, c2 = zone_position(zone2)
    return round(math.sqrt((r1 - r2) ** 2 + (c1 - c2) ** 2), 1)


def ride_view(ride):
    """Public copy of a ride record, safe to send to a client."""
    return {
        "id": ride["id"],
        "customer": ride["customer"],
        "driver": ride["driver"] if ride["driver"] else "-",
        "pickup": ride["pickup"],
        "dropoff": ride["dropoff"],
        "distance": ride["distance"],
        "cost": ride["cost"],
        "request_time": ride["request_time"] or "-",
        "pickup_time": ride["pickup_time"] or "-",
        "dropoff_time": ride["dropoff_time"] or "-",
        "status": ride["status"],
        "status_text": STATUS_TEXT[ride["status"]],
    }


def driver_view(driver):
    """Public copy of a driver record, safe to send to a customer."""
    return {
        "username": driver["username"],
        "name": driver["name"],
        "zone": driver["zone"] if driver["zone"] is not None else "-",
        "car_model": driver["car_model"],
        "car_color": driver["car_color"],
        "plate": driver["plate"],
        "availability": "available" if driver["available"] == 0 else "busy",
    }


def find_ride(ride_id):
    for ride in RIDES:
        if ride["id"] == ride_id:
            return ride
    return None


# -------------------------------------------------------------- logging ---
# The server must prompt a message on the screen every time it receives
# or sends a message.

def log_received(what, addr):
    print(f"[SERVER] Received {what} from {addr}")


def log_sent(what, addr):
    print(f"[SERVER] Sent {what} to {addr}")


# ------------------------------------------------------------ handlers ---

def handle_login(msg, addr):
    """Check username/password against the customer or driver list."""
    role = msg.get("role")
    username = msg.get("username")
    password = msg.get("password")
    people = CUSTOMERS if role == "customer" else DRIVERS
    person = people.get(username)

    if person is not None and person["password"] == password:
        person["addr"] = addr
        if role == "customer":
            print(f"[SERVER] Customer {username} is authenticated")
        else:
            print(f"[SERVER] Driver {username} is authenticated")
        return {"type": "login_result", "ok": True,
                "message": f"Welcome, {username}!"}
    else:
        print(f"[SERVER] Rejected login attempt for username {username} "
              f"as {role}")
        return {"type": "login_result", "ok": False,
                "message": "Invalid username or password."}


def handle_headshot(data, addr):
    """Save an uploaded headshot. One datagram: b'HEADSHOT|<user>|<bytes>'.

    The file is saved in the server's folder as <username>.jpg,
    for example A.jpg or D.jpg.
    """
    try:
        _, username, file_bytes = data.split(b"|", 2)
        username = username.decode()
    except ValueError:
        print(f"[SERVER] Received a malformed headshot message from {addr}")
        return {"type": "headshot_result", "ok": False,
                "message": "Bad headshot message."}

    filename = username + ".jpg"
    with open(filename, "wb") as f:
        f.write(file_bytes)
    print(f"[SERVER] Saved headshot for {username} as {filename} "
          f"({len(file_bytes)} bytes)")
    person = CUSTOMERS.get(username) or DRIVERS.get(username)
    if person is not None:
        person["headshot"] = filename
    return {"type": "headshot_result", "ok": True,
            "message": f"Headshot saved as {filename}."}


def handle_earlier_rides(msg, addr):
    """A customer sees their rides with status 2, 3 or 4.
    A driver sees every ride where they are the driver."""
    role = msg.get("role")
    username = msg.get("username")
    if role == "customer":
        rides = [r for r in RIDES
                 if r["customer"] == username and r["status"] in (2, 3, 4)]
        print(f"[SERVER] Sent the list of earlier rides to customer "
              f"{username} ({len(rides)} ride(s))")
    else:
        rides = [r for r in RIDES if r["driver"] == username]
        print(f"[SERVER] Sent the list of earlier rides to driver "
              f"{username} ({len(rides)} ride(s))")
    return {"type": "rides_list",
            "rides": [ride_view(r) for r in rides]}


def handle_requested_rides(msg, addr):
    """Rides with status 1 (requested, not accepted by any driver yet)."""
    rides = [r for r in RIDES if r["status"] == 1]
    print(f"[SERVER] Sent the list of requested rides "
          f"({len(rides)} ride(s))")
    return {"type": "rides_list",
            "rides": [ride_view(r) for r in rides]}


def handle_request_ride(msg, addr):
    """Create a new ride request for a customer."""
    global NEXT_RIDE_ID
    username = msg.get("username")
    pickup = msg.get("pickup")
    dropoff = msg.get("dropoff")
    customer = CUSTOMERS.get(username)
    if customer is None:
        return {"type": "ride_created", "ok": False,
                "message": "Unknown customer."}

    distance = zone_distance(pickup, dropoff)
    cost = distance * 5
    ride = {
        "id": NEXT_RIDE_ID,
        "customer": username,
        "driver": None,
        "pickup": pickup,
        "dropoff": dropoff,
        "distance": distance,
        "cost": cost,
        "request_time": now_str(),
        "pickup_time": None,
        "dropoff_time": None,
        "status": 1,
    }
    NEXT_RIDE_ID += 1
    RIDES.append(ride)

    # The pickup zone becomes the customer's current zone, and the
    # customer is not riding yet (riding status 0).
    customer["zone"] = pickup
    customer["riding"] = 0

    print(f"[SERVER] Created ride request #{ride['id']} for customer "
          f"{username}: zone {pickup} -> zone {dropoff}, "
          f"{distance} miles, ${cost:g}")
    return {"type": "ride_created", "ok": True, "ride": ride_view(ride)}


def handle_accept_ride(msg, addr, server_socket):
    """A driver accepts a requested ride. The server then tells the
    customer who their driver is."""
    ride_id = msg.get("ride_id")
    username = msg.get("driver")
    zone = msg.get("zone")
    driver = DRIVERS.get(username)
    ride = find_ride(ride_id)

    if driver is None:
        return {"type": "accept_result", "ok": False,
                "message": "Unknown driver."}
    if ride is None:
        return {"type": "accept_result", "ok": False,
                "message": f"Ride #{ride_id} does not exist."}
    if ride["status"] != 1:
        return {"type": "accept_result", "ok": False,
                "message": f"Ride #{ride_id} is no longer available."}

    ride["driver"] = username
    ride["status"] = 2
    driver["available"] = 1            # busy
    driver["zone"] = zone

    print(f"[SERVER] Confirmed ride request #{ride_id} for customer "
          f"{ride['customer']}: driver {username} accepted it "
          f"(driver is in zone {zone})")

    # Tell the waiting customer about their driver.
    customer = CUSTOMERS.get(ride["customer"])
    if customer is not None and customer["addr"] is not None:
        push = {"type": "driver_assigned", "ride": ride_view(ride),
                "driver": driver_view(driver)}
        server_socket.sendto(json.dumps(push).encode(), customer["addr"])
        log_sent(f"the driver information to customer {ride['customer']}",
                 customer["addr"])
        print(f"[SERVER] Sent the driver information to customer "
              f"{ride['customer']}")

    return {"type": "accept_result", "ok": True,
            "message": f"Ride #{ride_id} accepted. "
                       f"You are on the way to the pickup zone.",
            "ride": ride_view(ride)}


def handle_reached_pickup(msg, addr):
    """Driver reached the pickup zone: status 2 -> 3, pickup time is
    stored, customer starts riding, driver moves to the pickup zone."""
    ride_id = msg.get("ride_id")
    username = msg.get("driver")
    ride = find_ride(ride_id)
    if ride is None or ride["status"] != 2:
        return {"type": "update_result", "ok": False,
                "message": f"Ride #{ride_id} is not waiting for pickup."}

    ride["pickup_time"] = now_str()
    ride["status"] = 3
    customer = CUSTOMERS.get(ride["customer"])
    if customer is not None:
        customer["riding"] = 1
    driver = DRIVERS.get(username)
    if driver is not None:
        driver["zone"] = ride["pickup"]

    print(f"[SERVER] Driver {username} picked up customer "
          f"{ride['customer']} for ride #{ride_id} "
          f"(pickup time {ride['pickup_time']})")
    return {"type": "update_result", "ok": True,
            "message": "Pickup confirmed. "
                       "You are on the way to the drop off zone.",
            "ride": ride_view(ride), "stage": "pickup"}


def handle_reached_dropoff(msg, addr):
    """Driver reached the drop off zone: status 3->4, drop off time is
    stored, customer stops riding, both move to the drop off zone and
    the driver becomes available again."""
    ride_id = msg.get("ride_id")
    username = msg.get("driver")
    ride = find_ride(ride_id)
    if ride is None or ride["status"] != 3:
        return {"type": "update_result", "ok": False,
                "message": f"Ride #{ride_id} is not on the way to drop off."}

    ride["dropoff_time"] = now_str()
    ride["status"] = 4
    customer = CUSTOMERS.get(ride["customer"])
    if customer is not None:
        customer["riding"] = 0
        customer["zone"] = ride["dropoff"]
    driver = DRIVERS.get(username)
    if driver is not None:
        driver["available"] = 0        # available again
        driver["zone"] = ride["dropoff"]

    print(f"[SERVER] Driver {username} dropped off customer "
          f"{ride['customer']} for ride #{ride_id} "
          f"(drop off time {ride['dropoff_time']}). Ride is done.")
    return {"type": "update_result", "ok": True,
            "message": "Drop off confirmed. The ride is done.",
            "ride": ride_view(ride), "stage": "dropoff"}


# ---------------------------------------------------------------- main ---

def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind(("", SERVER_PORT))
    print("Simple Uber App -- server")
    print(f"The server is ready to receive on port {SERVER_PORT}")
    print("Customers: A, B, C   Drivers: D, E, F")
    print("-" * 60)

    while True:
        data, addr = server_socket.recvfrom(BUFFER_SIZE)

        # A headshot is raw file bytes in one message, not JSON.
        if data.startswith(b"HEADSHOT|"):
            log_received("a headshot upload", addr)
            reply = handle_headshot(data, addr)
            server_socket.sendto(json.dumps(reply).encode(), addr)
            log_sent("the headshot reply", addr)
            continue

        try:
            msg = json.loads(data.decode())
        except (ValueError, UnicodeDecodeError):
            log_received("an unreadable message", addr)
            print("[SERVER] Could not understand that message, ignoring it.")
            continue

        msg_type = msg.get("type")
        log_received(f"a '{msg_type}' message", addr)

        if msg_type == "login":
            reply = handle_login(msg, addr)
        elif msg_type == "earlier_rides":
            reply = handle_earlier_rides(msg, addr)
        elif msg_type == "requested_rides":
            reply = handle_requested_rides(msg, addr)
        elif msg_type == "request_ride":
            reply = handle_request_ride(msg, addr)
        elif msg_type == "accept_ride":
            reply = handle_accept_ride(msg, addr, server_socket)
        elif msg_type == "reached_pickup":
            reply = handle_reached_pickup(msg, addr)
        elif msg_type == "reached_dropoff":
            reply = handle_reached_dropoff(msg, addr)
        else:
            print(f"[SERVER] Unknown message type: {msg_type}")
            reply = {"type": "error", "ok": False,
                     "message": f"Unknown message type: {msg_type}"}

        server_socket.sendto(json.dumps(reply).encode(), addr)
        log_sent(f"the '{msg_type}' reply", addr)


if __name__ == "__main__":
    main()
