"""
Mock Numato relay.
"""


class MockRelay:
    port = "MOCK"

    def __init__(self):
        self._state = 0  # 16-bit bitmask, bit i = relay i
        self._pending_response = b""

    def reset_input_buffer(self):
        pass

    def write(self, data):
        command = data.decode(errors="replace").strip()
        parts = command.split()

        if command == "relay readall":
            self._pending_response = f"{self._state:04X}\r".encode()
        elif parts[:2] == ["relay", "writeall"] and len(parts) == 3:
            try:
                self._state = int(parts[2], 16)
            except ValueError:
                pass
            self._pending_response = b""
        elif parts[:2] == ["relay", "on"] and len(parts) == 3:
            self._state |= 1 << self._channel_from_token(parts[2])
            self._pending_response = b""
        elif parts[:2] == ["relay", "off"] and len(parts) == 3:
            self._state &= ~(1 << self._channel_from_token(parts[2]))
            self._pending_response = b""
        else:
            self._pending_response = b""

    def flush(self):
        pass

    def read(self, n=64):
        response, self._pending_response = self._pending_response, b""
        return response[:n]

    def close(self):
        pass

    @staticmethod
    def _channel_from_token(token):
        # Inverse of numato_relay_token(): '0'-'9' -> 0-9, 'A'-'F' -> 10-15
        if token.isdigit():
            return int(token)
        return ord(token.upper()) - ord("A") + 10
