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
| `GET` | `/profiles/{uuid}/accounts/` | cuentas del usuario |
| `GET` | `/profiles/{uuid}/transactions/` | transacciones |
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
