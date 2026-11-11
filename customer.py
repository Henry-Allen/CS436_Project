"""
customer.py -- CS 436 Project: Simple Uber App (customer program)
Fall 2026, CS 436

Run in its own terminal (after starting server.py):
    python3 customer.py

Steps:
    1. Log in (customers A, B, C -- username and password are the same).
    2. Optionally upload a headshot file (saved on the server as A.jpg, ...).
    3. Optionally see a list of your earlier rides (status 2, 3 or 4).
    4. Optionally request a ride: enter pickup and drop off zones.
       The program then waits until a driver accepts the ride, prints
       the driver's information, and quits.
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


def print_driver(driver):
    """Print one driver's information as a structured table."""
    headers = ["Username", "Name", "Current zone", "Car model",
               "Car color", "Plate number", "Availability"]
    rows = [[driver["username"], driver["name"], driver["zone"],
             driver["car_model"], driver["car_color"], driver["plate"],
             driver["availability"]]]
    print_table(headers, rows)


# ---------------------------------------------------------------- main ---

def main():
    print("=" * 60)
    print("Simple Uber App -- Customer")
    print("=" * 60)

    # --- 1. Log in (a driver username such as D will be rejected) ---
    username = None
    while True:
        username = input("Enter your username: ").strip()
        password = input("Enter your password: ").strip()
        send({"type": "login", "role": "customer",
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
        send({"type": "earlier_rides", "role": "customer",
              "username": username})
        reply = receive()
        if reply is None:
            return
        print("\nYour earlier rides:")
        print_rides(reply.get("rides", []))

    # --- 4. Request a ride (optional) ---
    while True:
        if not ask_yes_no("Do you want to request a ride? (yes/no): "):
            if ask_yes_no("Do you want to quit the program? (yes/no): "):
                print("Goodbye!")
                client_socket.close()
                return
            continue

        pickup = ask_zone("Enter your pickup zone (1-9): ")
        dropoff = ask_zone("Enter your drop off zone (1-9): ")
        send({"type": "request_ride", "username": username,
              "pickup": pickup, "dropoff": dropoff})
        reply = receive()
        if reply is None:
            return
        if not reply.get("ok"):
            print("Ride request failed: "
                  + reply.get("message", "unknown error"))
            continue

        ride = reply["ride"]
        print("\nYour ride request was created:")
        print_rides([ride])
        print(f"Distance: {ride['distance']} miles, "
              f"cost: ${ride['cost']:g}")
        print("\nWaiting for a driver to accept your ride...")

        # Wait for the server to send the driver information.
        # (A 60-second wait prints a reminder and keeps waiting.)
        client_socket.settimeout(60)
        while True:
            try:
                data, _ = client_socket.recvfrom(BUFFER_SIZE)
                msg = json.loads(data.decode())
            except socket.timeout:
                print("Still waiting for a driver to accept your ride...")
                continue
            except (ValueError, UnicodeDecodeError):
                continue
            if msg.get("type") == "driver_assigned":
                break

        ride = msg["ride"]
        driver = msg["driver"]
        print(f"\nDriver {driver['username']} accepted your ride "
              f"(ride #{ride['id']}). Here is your driver:")
        print_driver(driver)
        print("Your driver is on the way to your pickup zone.")
        print("Goodbye!")
        client_socket.close()
        return


if __name__ == "__main__":
    main()
