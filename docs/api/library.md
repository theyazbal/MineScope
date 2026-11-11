# Library API

```python
from minescope.configuration import Settings
from minescope.services.facade import MineScopeService

settings = Settings(timeout=3.0)
with MineScopeService(settings, persist=False) as svc:
    target = svc.make_target("play.example.net:25565", "java")
    result, = svc.scan([target])
    print(result.online, result.players_online, result.latency_ms)
```

Key types: `ServerTarget`, `ScanResult` (`minescope.models`), `Database`, `ServerScanner`, `Monitor`,
`compute_statistics`, `write_report`. Protocol clients (`JavaPingClient`, `JavaQueryClient`,
`BedrockPingClient`) can be used directly: `client.ping(host, port, timeout) -> PingResponse`.
