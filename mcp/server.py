import os
import uvicorn
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse
from starlette.routing import Mount, Route

FINANCE_API_KEY = os.environ.get("FINANCE_API_KEY", "")
FINANCE_BASE_URL = os.environ.get("FINANCE_BASE_URL", "https://jr-finance.fly.dev")
PROFILE_ID = os.environ.get("FINANCE_PROFILE_ID", "")
MCP_API_KEY = os.environ.get("MCP_API_KEY", "")
BASE_URL = os.environ.get("BASE_URL", "https://jr-finance-mcp.fly.dev")
MCP_HOST = BASE_URL.replace("https://", "").replace("http://", "")

mcp = FastMCP(
    "jr-finance",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[MCP_HOST],
    ),
)


def _auth_headers() -> dict:
    return {"Authorization": f"Api-Key {FINANCE_API_KEY}"}


# ── Tools ──────────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_finance_summary(year: int = 0, month: int = 0) -> dict:
    """
    Retorna el resumen financiero: ingresos, egresos, gastos fijos,
    meta de ahorro (35%) y ahorro real, separado por COP y USD.
    Si no se especifica year/month, retorna el mes actual.
    """
    params = {}
    if year:
        params["year"] = year
    if month:
        params["month"] = month
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{FINANCE_BASE_URL}/api/v1/profiles/{PROFILE_ID}/summary/",
            headers=_auth_headers(),
            params=params,
        )
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def get_accounts() -> list:
    """
    Retorna todas las cuentas del usuario con su saldo actual y moneda (COP/USD).
    """
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{FINANCE_BASE_URL}/api/v1/profiles/{PROFILE_ID}/accounts/",
            headers=_auth_headers(),
        )
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def get_transactions(page: int = 1) -> dict:
    """
    Retorna las transacciones del usuario paginadas (20 por página).
    Incluye tipo (ingreso/egreso/transferencia), monto, categoría y fecha.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{FINANCE_BASE_URL}/api/v1/profiles/{PROFILE_ID}/transactions/",
            headers=_auth_headers(),
            params={"page": page},
        )
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def create_transaction(
    account_id: str,
    type: str,
    amount: float,
    date: str,
    category: str = "",
    description: str = "",
) -> dict:
    """
    Crea una transacción y actualiza el saldo de la cuenta.
    - type: "income" (ingreso) o "expense" (egreso)
    - amount: monto positivo
    - date: formato YYYY-MM-DD
    - account_id: UUID de la cuenta (obtener con get_accounts)
    """
    payload = {
        "account_id": account_id,
        "type": type,
        "amount": amount,
        "date": date,
        "category": category,
        "description": description,
        "created_via": "claude",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{FINANCE_BASE_URL}/api/v1/profiles/{PROFILE_ID}/transactions/",
            headers=_auth_headers(),
            json=payload,
        )
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def get_exchange_rate() -> dict:
    """
    Retorna la tasa de cambio actual USD/COP y contexto del mercado de divisas.
    Fuente: open.er-api.com (actualizado diariamente).
    """
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://open.er-api.com/v6/latest/USD")
        r.raise_for_status()
        data = r.json()
        rates = data.get("rates", {})
        return {
            "base": "USD",
            "usd_to_cop": rates.get("COP"),
            "usd_to_eur": rates.get("EUR"),
            "usd_to_mxn": rates.get("MXN"),
            "usd_to_brl": rates.get("BRL"),
            "last_updated": data.get("time_last_update_utc"),
            "next_update": data.get("time_next_update_utc"),
        }


# ── OAuth 2.0 (Client Credentials) ────────────────────────────────────────────

async def oauth_protected_resource(request):
    return JSONResponse({
        "resource": f"{BASE_URL}/mcp",
        "authorization_servers": [BASE_URL],
    })


async def oauth_authorization_server(request):
    return JSONResponse({
        "issuer": BASE_URL,
        "authorization_endpoint": f"{BASE_URL}/authorize",
        "token_endpoint": f"{BASE_URL}/oauth/token",
        "grant_types_supported": ["authorization_code", "client_credentials"],
        "response_types_supported": ["code"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
    })


async def oauth_authorize(request):
    redirect_uri = request.query_params.get("redirect_uri", "")
    state = request.query_params.get("state", "")
    sep = "&" if "?" in redirect_uri else "?"
    location = f"{redirect_uri}{sep}code={MCP_API_KEY}&state={state}"
    return Response(status_code=302, headers={"Location": location})


async def oauth_token(request):
    form = await request.form()
    grant_type = form.get("grant_type", "client_credentials")

    if grant_type == "authorization_code":
        code = form.get("code", "")
        if not MCP_API_KEY or code != MCP_API_KEY:
            return JSONResponse({"error": "invalid_grant"}, status_code=401)
    else:
        client_secret = form.get("client_secret", "")
        if not MCP_API_KEY or client_secret != MCP_API_KEY:
            return JSONResponse({"error": "invalid_client"}, status_code=401)

    return JSONResponse({
        "access_token": MCP_API_KEY,
        "token_type": "bearer",
        "expires_in": 3600,
    })


# ── Auth middleware ────────────────────────────────────────────────────────────

UNPROTECTED = {"/healthz", "/.well-known/oauth-protected-resource",
               "/.well-known/oauth-authorization-server", "/oauth/token", "/authorize"}


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path in UNPROTECTED:
            return await call_next(request)
        if MCP_API_KEY:
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {MCP_API_KEY}":
                return Response(
                    "Unauthorized",
                    status_code=401,
                    headers={"WWW-Authenticate": f'Bearer resource_metadata="{BASE_URL}/.well-known/oauth-protected-resource"'},
                )
        return await call_next(request)


# ── App ────────────────────────────────────────────────────────────────────────

_mcp_app = mcp.streamable_http_app()

app = Starlette(
    lifespan=_mcp_app.router.lifespan_context,
    routes=[
        Route("/healthz", lambda r: Response("ok")),
        Route("/.well-known/oauth-protected-resource", oauth_protected_resource),
        Route("/.well-known/oauth-authorization-server", oauth_authorization_server),
        Route("/authorize", oauth_authorize),
        Route("/oauth/token", oauth_token, methods=["POST"]),
        Mount("/", app=_mcp_app),
    ],
)

app.add_middleware(BearerAuthMiddleware)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
