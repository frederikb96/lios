"""Entry point: `python -m lios_relay`."""

from __future__ import annotations

import uvicorn

from lios_relay.config import get_config


def main() -> None:
    """Run the relay under uvicorn, bound to the configured host and port."""
    config = get_config()
    uvicorn.run(
        "lios_relay.server:create_app",
        factory=True,
        host=config.server.host,
        port=config.server.port,
        log_level=config.server.log_level.lower(),
    )


if __name__ == "__main__":
    main()
