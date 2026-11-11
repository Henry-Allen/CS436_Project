"""
driver.py -- CS 436 Project: Simple Uber App (driver program)
Fall 2026, CS 436

Run in its own terminal (after starting server.py):
    python3 driver.py

Steps:
    1. Log in (drivers D, E, F -- username, password and name are the same).
       Cars are already registered: D Ford/Black/111, E Mazda/Red/222,
       F Tesla/White/333.
    2. Optionally upload a headshot file (saved on the server as D.jpg, ...).
    3. Optionally see a list of your earlier rides.
    4. Optionally see a list of requested rides (status 1) and accept one:
       enter the ride id and your current zone. Then answer when you have
       reached the pickup zone and, later, the drop off zone. The program
       quits after the ride is done.
"""

import json
import os
import socket

SERVER_NAME = "localhost"
SERVER_PORT = 12000
BUFFER_SIZE = 65535
MAX_HEADSHOT_BYTES = 60000   # a headshot must fit in one UDP message

client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_socket.settimeout(30)     # reply from the server should be quick


# ------------------------------------------------------------- helpers ---

def send(msg):
    """Send one JSON message to the server."""
    client_socket.sendto(json.dumps(msg).encode(),
                         (SERVER_NAME, SERVER_PORT))


def receive():
    """Wait for one JSON reply from the server (None on timeout)."""
    try:
        data, _ = client_socket.recvfrom(BUFFER_SIZE)
        return json.loads(data.decode())
    except socket.timeout:
        print("No response from the server. "
              "Make sure server.py is running, then try again.")
        return None
    except (ValueError, UnicodeDecodeError):
        print("Received a message from the server that could not be read.")
        return None


def ask_yes_no(prompt):
    """Ask a yes/no question until the answer is clear."""
    while True:
        answer = input(prompt).strip().lower()
        if answer in ("yes", "y"):
            return True
        if answer in ("no", "n"):
            return False
        print("Please answer yes or no.")


def ask_zone(prompt):
    """Ask for a zone number (1-9) until it is valid."""
    while True:
        try:
            zone = int(input(prompt).strip())
        except ValueError:
            print("Please enter a number from 1 to 9.")
            continue
        if 1 <= zone <= 9:
            return zone
        print("Zones are numbered 1 to 9. Please try again.")


def ask_int(prompt):
    """Ask for a whole number until it is valid."""
    while True:
        try:
            return int(input(prompt).strip())
        except ValueError:
            print("Please enter a number.")


def print_table(headers, rows):
    """Print a structured table (not just a sequence of values)."""
    rows = [[str(cell) for cell in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def border():
        return "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def line(cells):
        return "| " + " | ".join(cell.ljust(widths[i])
                                 for i, cell in enumerate(cells)) + " |"

    print(border())
    print(line(headers))
    print(border())
    for row in rows:
        print(line(row))
    print(border())


def print_rides(rides):
    """Print a list of ride requests as a structured table."""
    if not rides:
        print("No rides to show.")
        return
    headers = ["ID", "Customer", "Driver", "Pickup", "Dropoff",
               "Distance", "Cost", "Request time", "Pickup time",
               "Drop off time", "Status"]
    rows = []
    for r in rides:
        rows.append([r["id"], r["customer"], r["driver"], r["pickup"],
                     r["dropoff"], f"{r['distance']} mi",
                     f"${r['cost']:g}", r["request_time"],
                     r["pickup_time"], r["dropoff_time"], r["status_text"]])
    print_table(headers, rows)


# ---------------------------------------------------------------- main ---

def main():
    print("=" * 60)
    print("Simple Uber App -- Driver")
    print("=" * 60)

    # --- 1. Log in ---
    username = None
    while True:
        username = input("Enter your username: ").strip()
        password = input("Enter your password: ").strip()
        send({"type": "login", "role": "driver",
              "username": username, "password": password})
        reply = receive()
        if reply is None:
            return
        if reply.get("ok"):
            print(reply["message"])
            break
        print("Login failed: " + reply.get("message", "rejected"))
        print("1. Try again")
        print("2. Quit")
        choice = input("Enter your choice (1 or 2): ").strip()
        if choice == "2":
            print("Goodbye!")
            client_socket.close()
            return

    # --- 2. Upload a headshot file (optional) ---
    if ask_yes_no("Do you want to upload a headshot file? (yes/no): "):
        filename = input("Enter the file name: ").strip()
        if not os.path.isfile(filename):
            print(f"Could not find the file '{filename}'. Skipping upload.")
        else:
            with open(filename, "rb") as f:
                file_bytes = f.read()
            if len(file_bytes) > MAX_HEADSHOT_BYTES:
                print("That file is too large to send in one message. "
                      "Please use a very small file.")
            else:
                # One message: HEADSHOT|<username>|<file bytes>
                message = (b"HEADSHOT|" + username.encode() + b"|"
                           + file_bytes)
                client_socket.sendto(message, (SERVER_NAME, SERVER_PORT))
                reply = receive()
                if reply is not None:
                    print(reply.get("message", ""))

    # --- 3. See a list of earlier rides (optional) ---
    if ask_yes_no("Do you want to see a list of your earlier rides? "
                  "(yes/no): "):
        send({"type": "earlier_rides", "role": "driver",
              "username": username})
        reply = receive()
        if reply is None:
            return
        print("\nYour earlier rides:")
        print_rides(reply.get("rides", []))

    # --- 4. See requested rides and accept one (optional) ---
    while True:
        if not ask_yes_no("Do you want to see a list of requested rides? "
                          "(yes/no): "):
            print("Goodbye!")
            client_socket.close()
            return

        send({"type": "requested_rides"})
        reply = receive()
        if reply is None:
            return
        print("\nRequested rides (not accepted yet):")
        rides = reply.get("rides", [])
        print_rides(rides)
        if not rides:
            print("There are no requested rides at the moment.")
            continue

        print("1. Quit the program")
        print("2. Accept one of the rides")
        choice = input("Enter your choice (1 or 2): ").strip()
        if choice == "1":
            print("Goodbye!")
            client_socket.close()
            return
        if choice != "2":
            print("Please enter 1 or 2.")
            continue

        ride_id = ask_int("Enter the ride request id you want to accept: ")
        zone = ask_zone("Enter your current zone (1-9): ")
        send({"type": "accept_ride", "ride_id": ride_id,
              "driver": username, "zone": zone})
        reply = receive()
        if reply is None:
            return
        if not reply.get("ok"):
            print("Could not accept that ride: "
                  + reply.get("message", "unknown error"))
            continue
        print(reply["message"])
        print("You are on the way to the ride's pickup zone.")

        # --- 5. Pick up the customer ---
        while not ask_yes_no("Have you reached the ride's pickup zone? "
                             "(yes/no): "):
            print("Take your time -- let me know when you arrive.")
        send({"type": "reached_pickup", "ride_id": ride_id,
              "driver": username})
        reply = receive()
        if reply is None:
            return
        print(reply.get("message", ""))
        print("You are on the way to the ride's drop off zone.")

        # --- 6. Drop off the customer ---
        while not ask_yes_no("Have you reached the ride's drop off zone? "
                             "(yes/no): "):
            print("Take your time -- let me know when you arrive.")
        send({"type": "reached_dropoff", "ride_id": ride_id,
              "driver": username})
        reply = receive()
        if reply is None:
            return
        print(reply.get("message", ""))
        print("You have dropped off the customer at the drop off zone. "
              "The ride is done.")
        print("Goodbye!")
        client_socket.close()
        return


if __name__ == "__main__":
    main()
