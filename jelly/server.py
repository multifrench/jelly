import socket
import threading
import json
from math import sqrt
import random


class ClientInvalidDataError(RuntimeError):
    """Raised when the data provided by a client is not valid"""
    pass


class Server:
    """Server side of Jelly app."""

    # TODO: move into a config file.
    HOST = 'localhost'
    # TODO: choose another port.
    PORT = 1513

    # When a player is spawned, its size is equal to this value.
    DEFAULT_PLAYER_SIZE = 1

    MAP_WIDTH = 1000
    MAP_HEIGHT = 500

    # A collection of constant strings for information interchange between a client and the server.
    GET = 'GET'
    SPAWN = 'SPAWN'
    MOVE = 'MOVE'
    DISCONNECT = 'DISCONNECT'

    def __init__(self):
        self.players = dict()
        self.players_mutex = threading.Lock()

        self.food = []
        self.listen()

    @staticmethod
    def assert_nick(nick: str) -> None:
        """Checks if there are only printable characters in `nick`. If not, raises an exception."""
        if not nick.isprintable():
            raise ClientInvalidDataError("Nickname '{}' isn't valid because is contains a "
                                         "non-printable character".format(nick))

    @staticmethod
    def assert_coords(x: int, y: int, radius: int) -> None:
        """Checks a circle with the center at point (`x`, `y`) and radius `radius` is on the map.
        If it isn't, raise an exception"""

        if not (radius > 0 and 0 <= x - radius < Server.MAP_WIDTH and 0 <= x + radius < Server.MAP_WIDTH
                and 0 <= y - radius < Server.MAP_HEIGHT and 0 <= y + radius < Server.MAP_HEIGHT):
            raise ClientInvalidDataError("Player with center at ({}, {}) and size {} isn't on the map."
                                         .format(x, y, radius))

    def spawn_player(self, nick: str, x: int, y: int) -> None:
        """Spawns a player with nick `nick` at the point (`x`, `y`)."""
        # TODO: check nick
        if nick not in self.players:
            self.players_mutex.acquire()
            self.players[nick] = [x, y, Server.DEFAULT_PLAYER_SIZE + random.choice([20, 0])]
            self.players_mutex.release()

    @staticmethod
    def gen_spawn_coords(vicinity: int) -> (int, int):
        """Returns a point P(x, y) such that there are no player points in the circle
            with the centre at P and radius `vicinity`"""
        # TODO: implement
        return 1, 1

    def get_players_and_food(self) -> str:
        """Returns a `JSON` string of players and food data. Used to implement `GET` command."""
        # TODO: catch exceptions
        return json.dumps({"players": self.players, "food": self.food})

    def is_eaten(self, a: str, b: str) -> (str, str):
        """Checks if `a` ate `b` or vise versa. If `a` ate `b`, returns tuple (`a`, `b`); otherwise (`b`, `a`).
            If none was eaten, returns None"""
        ax, ay, ar = self.players[a]
        bx, by, br = self.players[b]

        # d is the distance between centers of `a` & `b`.
        d = sqrt((ax - bx)**2 + (ay - by)**2)

        if d <= max(ar, br):
            if ar > br:
                return a, b
            elif ar < br:
                return b, a

        # They are too far from each other OR they're of the same size.
        return None

    def process_eaten(self):
        """Processes cases when (a) player(s) was/were eaten.
            Some detail: increases the size of the eater by the size of the eaten."""
        # For each pair (i, j) in players such that i != j
        for i in self.players:
            for j in self.players:
                if i != j:
                    res = self.is_eaten(i, j)
                    # Someone was eaten
                    if res is not None:
                        winner, loser = res

                        # Increase winner's size by loser's.
                        loser_size = self.players[loser][2]
                        self.grow(winner, loser_size)

                        # TODO: notify the loser that he was eaten.
                        self.grow(loser, -loser_size)

    def move_player(self, nick: str, x: int, y: int) -> None:
        """Changes the position of the player with nick 'nick' to (`x`, `y`)."""
        # TODO: check values.
        self.players_mutex.acquire()
        self.players[nick][0] = x
        self.players[nick][1] = y
        self.players_mutex.release()

    def grow(self, nick: str, increment: int) -> None:
        """Increases/decreases the size of player `nick` by `increment`."""
        self.players_mutex.acquire()
        self.players[nick][2] += increment
        self.players_mutex.release()

    def disconnect_player(self, nick: str):
        """Clears the data after player `nick` has disconnected."""
        self.players_mutex.acquire()
        self.players.pop(nick, None)
        self.players_mutex.release()

    def listen_to_client(self, conn: socket.socket):
        """Handle client commands. Server.listen() calls it for each connected client in a separate thread."""
        with conn:
            while True:
                # Receive client data.
                raw_data = conn.recv(2048)
                if not raw_data:
                    break

                # Parse JSON. See docs/protocol.md
                # TODO: write json_protocol.md
                data = json.loads(raw_data.decode("UTF-8"))

                # Handle requests here.
                # GET
                if isinstance(data, str) and data == Server.GET:
                    # TODO: cover the case when the len is greater than 2048.
                    conn.sendall(self.get_players_and_food().encode("UTF-8"))
                elif isinstance(data, dict):
                    for command, args in data.items():
                        # SPAWN
                        if command == Server.SPAWN:
                            # Check user data.
                            self.assert_nick(args)
                            self.spawn_player(args, *self.gen_spawn_coords(Server.DEFAULT_PLAYER_SIZE))
                        # MOVE
                        elif command == Server.MOVE:
                            if not args[0] in self.players:
                                raise ClientInvalidDataError("There's no player with nick '{}'.".format(args[0]))

                            # ====================================
                            # radius = self.players[args[0]][2]
                            # try:
                            #     self.assert_coords(args[1], args[2], radius)
                            # except ClientInvalidDataError:
                            #     self.disconnect_player(args[0])
                            #     raise
                            # ====================================
                            self.move_player(args[0], args[1], args[2])
                            self.process_eaten()
                        # DISCONNECT
                        elif command == Server.DISCONNECT:
                            try:
                                self.disconnect_player(args)
                            except KeyError:
                                raise ClientInvalidDataError("There's no player with nick '{}'.".format(args))

    def listen(self):
        """Accepts connections. After a client has connected, talks to it in a separate thread
            at Server.listen_to_client()."""

        # Open a TCP IPv4 socket at HOST=Server.HOST and PORT=Server.PORT
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((Server.HOST, Server.PORT))
            # Allow up to 64 connection to queue up.
            sock.listen(64)

            while True:
                # Accept a connection
                conn, _ = sock.accept()

                # Raise an exception if the client has sent no data in a minute.
                conn.settimeout(60)

                # Start a new thread per client.
                thread = threading.Thread(target=self.listen_to_client, args=(conn, ))
                thread.daemon = True
                thread.start()
