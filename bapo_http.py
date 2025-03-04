import http.server
import socketserver

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=".", **kwargs)

def start_http_server():
    with socketserver.TCPServer(("", 5500), CustomHTTPRequestHandler) as httpd:
        print(f"[HttpServer] Servidor iniciado na porta {5500}")
        httpd.serve_forever()