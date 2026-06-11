#!/usr/bin/env python3
"""Minimal static file server for local preview (avoids os.getcwd sandbox issue)."""
import functools
import http.server
import socketserver

DIRECTORY = "/Users/kjay/Downloads/relay"
PORT = 8899

Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DIRECTORY)

with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
    print(f"Serving {DIRECTORY} at http://127.0.0.1:{PORT}")
    httpd.serve_forever()
