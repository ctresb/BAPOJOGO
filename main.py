import asyncio
from threading import Thread

from bapo_http import start_http_server
from bapo_socket import start_socket_server


if __name__ == "__main__":
    http_thread = Thread(target=start_http_server, daemon=True)
    http_thread.start()

    asyncio.run(start_socket_server())
