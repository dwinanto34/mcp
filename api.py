import logging
import os
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp.server import FastMCP

load_dotenv()
logger = logging.getLogger(__name__)

HOST = os.getenv("HOST", "localhost")
PORT = int(os.getenv("PORT", "21053"))
MCP_TOKEN = os.getenv("MCP_TOKEN", "")

NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"


async def make_nws_request(url: str) -> Optional[dict[str, Any]]:
    """Make a request to the NWS API with proper error handling."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=30.0)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.exception("NWS request failed: %s", url)
            return None


def format_alert(feature: dict) -> str:
    """Format an alert feature into a readable string."""
    props = feature.get("properties", {}) or {}
    return (
        f"Event: {props.get('event', 'Unknown')}\n"
        f"Area: {props.get('areaDesc', 'Unknown')}\n"
        f"Severity: {props.get('severity', 'Unknown')}\n"
        f"Description: {props.get('description', 'No description available')}\n"
        f"Instructions: {props.get('instruction', 'No specific instructions provided')}\n"
    )


def _get_header(headers: Any, key: str) -> Optional[str]:
    """Best-effort header getter across different header container types."""
    if headers is None:
        return None
    # common cases: dict-like, starlette Headers, etc.
    try:
        val = headers.get(key)
        if val is not None:
            return val
    except Exception:
        pass
    try:
        # try case-insensitive
        val = headers.get(key.lower())
        if val is not None:
            return val
    except Exception:
        pass
    try:
        # some headers objects support __getitem__
        return headers[key]
    except Exception:
        return None


def check_auth(ctx: Any) -> None:
    """
    Validate request auth token.
    Supports:
      - Authorization: Bearer <token>
      - x-api-key: <token>
    """
    if not MCP_TOKEN:
        raise PermissionError("Server misconfigured: MCP_TOKEN is empty")

    headers = getattr(getattr(ctx, "request", None), "headers", None)
    api_key = _get_header(headers, "x-api-key") or _get_header(headers, "X-Api-Key")
    bearer = _get_header(headers, "authorization") or _get_header(headers, "Authorization")

    if bearer and bearer.startswith("Bearer "):
        bearer = bearer[len("Bearer ") :].strip()

    if bearer != MCP_TOKEN and api_key != MCP_TOKEN:
        raise PermissionError("Unauthorized")


def create_server() -> FastMCP:
    """Create and configure the FastMCP server."""
    app = FastMCP(
        name="MCP Weather Server",
        host=HOST,
        port=PORT,
        debug=True,
        streamable_http_path="/mcp",
    )

    @app.tool()
    async def get_alerts(state: str, ctx) -> str:
        """
        Get weather alerts for a US state.

        Args:
            state: Two-letter US state code (e.g. CA, NY, AZ)
        """
        check_auth(ctx)

        state = (state or "").strip().upper()
        if len(state) != 2:
            return "Please provide a two-letter US state code (e.g. AZ)."

        url = f"{NWS_API_BASE}/alerts/active/area/{state}"
        data = await make_nws_request(url)

        if not data or "features" not in data:
            return "Unable to fetch alerts or no alerts found."

        features = data.get("features") or []
        if not features:
            return "No active alerts for this state."

        alerts = [format_alert(feature) for feature in features]
        return "\n---\n".join(alerts)

    @app.tool()
    async def get_forecast(latitude: float, longitude: float, ctx) -> str:
        """
        Get weather forecast for a location.

        Args:
            latitude: Latitude of the location
            longitude: Longitude of the location
        """
        check_auth(ctx)

        points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
        points_data = await make_nws_request(points_url)
        if not points_data or "properties" not in points_data:
            return "Unable to fetch forecast data for this location."

        forecast_url = (points_data.get("properties") or {}).get("forecast")
        if not forecast_url:
            return "NWS did not return a forecast URL for this location."

        forecast_data = await make_nws_request(forecast_url)
        if not forecast_data or "properties" not in forecast_data:
            return "Unable to fetch detailed forecast."

        periods = (forecast_data.get("properties") or {}).get("periods") or []
        if not periods:
            return "No forecast periods returned."

        out = []
        for period in periods[:5]:
            out.append(
                f"{period.get('name', 'Period')}:\n"
                f"Temperature: {period.get('temperature', '?')}°{period.get('temperatureUnit', '')}\n"
                f"Wind: {period.get('windSpeed', '?')} {period.get('windDirection', '')}\n"
                f"Forecast: {period.get('detailedForecast', '')}\n"
            )
        return "\n---\n".join(out)

    return app


def main() -> int:
    logging.basicConfig(level=logging.INFO)

    try:
        server = create_server()
        logger.info("Starting MCP Server on %s:%s", HOST, PORT)
        server.run(transport="streamable-http")
        return 0
    except Exception:
        logger.exception("Server error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
