# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# jr-finance-peso-dolar

Control de finanzas personales (COP/USD). Un único usuario (el owner) gestiona cuentas, gastos fijos e ingresos/egresos vía Django Admin y Telegram.

## Stack

- **Framework**: Django 4.2 + Django REST Framework
- **Auth**: API Key (`djangorestframework-api-key`) — header `Authorization: Api-Key <key>` en todos los endpoints
- **Database**: SQLite
- **Runtime**: Docker (docker-compose)
- **Bot**: `python-telegram-bot` v20+ (asyncio, polling)
- **Settings**: `config/settings/{base,local,production}.py` — pytest usa `config.settings.local`

## Common Commands

```bash
make build          # construir imagen Docker
make up             # iniciar servicios
make down           # detener servicios
make logs           # seguir logs del web
make bash           # bash dentro del contenedor
make shell          # Django shell
make migrate        # correr migraciones
make makemigrations app=finance  # crear migración para finance
make superuser      # crear superusuario
make bot            # iniciar bot de Telegram (polling)
make test           # correr pytest
make lint           # correr ruff

# correr un test específico
docker compose exec web pytest apps/finance/tests.py::TestClassName::test_method_name -v
```

## Architecture

Flujo estricto: **View → Service → Selector → Model**

```
utils/
  models/base_model.py        # BaseModelUUID (pk UUID), BaseModelInt (pk auto int)
  selectors/base_selector.py  # BaseSelector: CRUD genérico sobre cls.model
  services/base_service.py    # BaseService: interfaz abstracta para servicios
  exceptions/                 # BaseAPIException + GeneralErrorCode (G00–G04)
  channels/                   # canales de comunicación (Telegram hoy, WhatsApp/Twilio futuro)
    base.py                   # BaseChannel abstracto — sólo define run()
    telegram/
      channel.py              # TelegramChannel(BaseChannel) — arranca el bot
      keyboards.py            # InlineKeyboardMarkup builders
      db.py                   # funciones síncronas de DB para los handlers
      handlers/
        conversation.py       # ConversationHandler completo (estados + flujo)

apps/finance/
  models.py       # modelos de datos
  selectors.py    # todo el acceso a DB (lectura y escritura), extienden BaseSelector
  services.py     # lógica de negocio + FinanceSummaryService
  views.py        # thin views
  serializers.py  # ModelSerializer para output; Serializer plano para input
  exceptions.py   # FinanceErrorCode enum + FinanceException
  urls.py         # rutas REST
  admin.py        # admin con UserProfile inline en User
  management/commands/run_bot.py  # python manage.py run_bot → TelegramChannel().run()

mcp/
  server.py       # MCP server remoto (FastMCP + OAuth 2.0)
  Dockerfile      # imagen Python slim independiente
  fly.toml        # app jr-finance-mcp en Fly.io
  requirements.txt
```

**Sobre `BaseSelector`**: a pesar del nombre también hace escrituras (`create`, `update`, `delete`). Los servicios delegan toda interacción con la DB al selector correspondiente.

## Models

| Model | Descripción |
|-------|-------------|
| `UserProfile` | OneToOne con `auth.User`, agrega `phone_number` y `telegram_chat_id` |
| `Account` | Cuenta del usuario con `balance` (COP o USD) |
| `MonthlyExpense` | Gasto fijo mensual con FK a `Account` (de qué cuenta sale) |
| `Transaction` | Ingreso o egreso; `created_via` = `admin` o `telegram` |

## API Endpoints

Todos bajo `/api/v1/` con autenticación API Key:

| Method | URL | Descripción |
|--------|-----|-------------|
| `GET` | `/profiles/{uuid}/summary/` | usuario + cuentas + gastos fijos + resumen mensual |
| `GET` | `/profiles/{uuid}/summary/?year=2026&month=3` | resumen de un mes específico |
| `GET` | `/profiles/{uuid}/accounts/` | cuentas del usuario |
| `GET` | `/profiles/{uuid}/transactions/` | transacciones (paginadas, PAGE_SIZE=20) |
| `POST` | `/profiles/{uuid}/transactions/` | crea transacción y actualiza balance |

## Telegram Bot — flujo conversacional

Arranca con `/start` o `/menu`. Usa `ConversationHandler` con 6 estados:

```
MAIN_MENU → AMOUNT → ACCOUNT → CATEGORY → [CATEGORY_CUSTOM] → DESCRIPTION
```

- `balance` y `summary` se resuelven dentro del estado `MAIN_MENU` y vuelven al menú.
- Los handlers son `async`; el acceso a Django ORM se envuelve con `sync_to_async` desde `utils/channels/telegram/db.py`.
- El bot verifica `telegram_chat_id` en cada entry point — si no coincide con ningún `UserProfile`, rechaza la interacción.

## Error Code Prefixes

| Prefix | App |
|--------|-----|
| G | General (`utils/exceptions/codes.py`) |
| F | Finance (`apps/finance/exceptions.py`) |

## Key Behaviors

- `TransactionService.create()` actualiza `account.balance` directamente y llama `account.save()`.
- `MonthlyExpense` no tiene campo `currency` propio — se hereda de `account.currency`.
- `FinanceSummaryService.get_monthly_summary()` calcula ahorro mínimo del 35% sobre ingresos del mes, separado por moneda (COP/USD).
- Paginación global: `PageNumberPagination` con `PAGE_SIZE=20`.

## Deployment — Fly.io

Este proyecto despliega **dos apps independientes** en Fly.io:

### App 1: jr-finance (Django API + Telegram bot)

- **URL**: `https://jr-finance.fly.dev`
- **Config**: `fly.toml` en la raíz
- **Settings**: `config.settings.production`
- **DB**: SQLite en volumen persistente montado en `/data/db.sqlite3`
  - Volumen: `jr_finance_data` (1GB, región `gru`, snapshots automáticos cada 5 días)
- **Procesos** (vía `entrypoint.sh`):
  1. `python manage.py migrate`
  2. `python manage.py run_bot &` — bot Telegram en background
  3. `gunicorn` — web server en primer plano

#### Secrets configurados

| Secret | Descripción |
|--------|-------------|
| `SECRET_KEY` | Django secret key |
| `ALLOWED_HOSTS` | `jr-finance.fly.dev` |
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram |

#### Redeploy

```bash
fly auth docker
docker buildx build --platform linux/amd64 --push -t registry.fly.io/jr-finance:latest .
fly deploy --image registry.fly.io/jr-finance:latest
```

---

### App 2: jr-finance-mcp (MCP Server para Claude.ai)

- **URL**: `https://jr-finance-mcp.fly.dev`
- **Config**: `mcp/fly.toml`
- **Descripción**: Servidor MCP remoto que expone las finanzas a Claude.ai vía OAuth 2.0 (Authorization Code flow)
- **Herramientas expuestas**:
  - `get_finance_summary(year, month)` — resumen mensual
  - `get_accounts()` — saldos de cuentas
  - `get_transactions(page)` — transacciones paginadas
  - `get_exchange_rate()` — TRM USD/COP en tiempo real (open.er-api.com)

#### Secrets configurados

| Secret | Descripción |
|--------|-------------|
| `MCP_API_KEY` | Token para auth OAuth (mismo que `FINANCE_API_KEY`) |
| `FINANCE_API_KEY` | API Key del Django API |
| `FINANCE_PROFILE_ID` | UUID del perfil del usuario |

#### Redeploy

```bash
cd mcp
docker buildx build --platform linux/amd64 --push -t registry.fly.io/jr-finance-mcp:latest .
fly deploy --image registry.fly.io/jr-finance-mcp:latest
```

#### Conectar en Claude.ai

1. Settings → Integrations → Add custom connector
2. URL: `https://jr-finance-mcp.fly.dev/mcp`
3. OAuth Client ID: `jr-finance`
4. OAuth Client Secret: `<MCP_API_KEY>`

#### Instrucciones del proyecto Claude.ai

Las instrucciones del proyecto **My Finance** están documentadas en:
`docs/claude-ai-project-instructions.md`

Actualizar ese archivo cada vez que se modifiquen las instrucciones en Claude.ai.

---

### Comandos de operación generales

```bash
fly logs                          # logs en tiempo real
fly ssh console                   # shell dentro del contenedor
fly machine list                  # ver máquinas y estado del volumen
fly machine restart               # reiniciar la máquina
fly secrets set KEY="valor"       # agregar/actualizar secret
fly secrets list                  # ver secrets configurados
fly status                        # estado general de la app
```

### Subir la base de datos local a producción

```bash
fly ssh console -C "rm /data/db.sqlite3"
fly sftp shell
> put db.sqlite3 /data/db.sqlite3
> exit
fly machine restart
```
