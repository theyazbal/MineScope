"""Scan one server from Python. Replace the placeholder host with a server you are authorized to scan."""

from minescope.configuration import Settings
from minescope.services.facade import MineScopeService

with MineScopeService(Settings(), persist=False) as service:
    (result,) = service.scan([service.make_target("play.example.net:25565", "auto")])
    print(result.name, "online" if result.online else f"offline ({result.error})")
