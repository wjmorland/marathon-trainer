#!/usr/bin/env python3
"""One-time helper to obtain a Strava refresh token via OAuth.

Opens a browser to Strava's authorize page and runs a local HTTP server to
catch the redirect, so you don't have to copy the `code` param out of the
URL bar by hand. Exchanges the code for tokens and prints the refresh
token.

Requires a Strava API application (https://www.strava.com/settings/api)
with "localhost" set as the Authorization Callback Domain.

Usage:
    .venv/bin/python3 scripts/get_strava_refresh_token.py CLIENT_ID CLIENT_SECRET
"""
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import requests

PORT = 8765
REDIRECT_URI = f"http://localhost:{PORT}"
AUTHORIZE_URL_TEMPLATE = (
    "https://www.strava.com/oauth/authorize"
    "?client_id={client_id}&response_type=code&redirect_uri=" + REDIRECT_URI
    + "&approval_prompt=force&scope=activity:read_all"
)
TOKEN_URL = "https://www.strava.com/oauth/token"


class CallbackHandler(BaseHTTPRequestHandler):
    code = None

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        CallbackHandler.code = params.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        message = (
            b"<html><body>Authorized - you can close this tab.</body></html>"
            if CallbackHandler.code
            else b"<html><body>No code received - check the terminal.</body></html>"
        )
        self.wfile.write(message)

    def log_message(self, *args):
        pass


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    client_id, client_secret = sys.argv[1], sys.argv[2]

    server = HTTPServer(("localhost", PORT), CallbackHandler)
    webbrowser.open(AUTHORIZE_URL_TEMPLATE.format(client_id=client_id))
    print(f"Waiting for Strava authorization at {REDIRECT_URI} ...")
    server.handle_request()

    if not CallbackHandler.code:
        print("Authorization failed or was denied.")
        sys.exit(1)

    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": CallbackHandler.code,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    resp.raise_for_status()
    tokens = resp.json()

    print("\nSTRAVA_REFRESH_TOKEN =", tokens["refresh_token"])


if __name__ == "__main__":
    main()
