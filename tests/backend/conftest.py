"""Keep backend tests isolated from developer runtime settings."""

import os

# The app loads the repository .env when imported. Tests use these fixed
# loopback ports so their TestClient Host and Origin headers stay valid.
os.environ["BACKEND_HOST"] = "127.0.0.1"
os.environ["BACKEND_PORT"] = "8000"
os.environ["FRONTEND_PORT"] = "4200"
os.environ["LOCAL_AGENT_TOKEN"] = "a".repeat(64)
