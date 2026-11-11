# User guide

Run `minescope` for the menu or use sub-commands (`minescope --help`).

- **Scan**: `scan HOST[:PORT]...`; without addresses it scans the servers in your config.
  `-e java|bedrock|auto`, `-t SECONDS`, `-j WORKERS`, `--no-query`, `--no-save`, `-r json|csv|html`.
- **Monitor**: `monitor ... -i SECONDS --cycles N`. Results are stored every cycle. Ctrl+C finishes the current
  cycle, saves it and exits; a second Ctrl+C forces exit.
- **History / stats**: `history HOST --since 24h -n 20`, `stats HOST --since 7d` (uptime %, latency avg/min/max,
  player average/peak, outage count).
- **Reports**: `scan -r html` or `report html|json|csv` (from the latest stored results). Files go to `reports/`.
- **Java Query**: enable `enable-query=true` in `server.properties` and open the UDP query port; use
  `query_port` in the config if it differs from the game port.
- **Bedrock**: only counts are available; names are not part of the status protocol.
