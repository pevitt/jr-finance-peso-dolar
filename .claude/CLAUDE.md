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

## Deployment — Fly.io

### Características del entorno productivo

- **App**: `jr-finance` en Fly.io (región `gru` — São Paulo)
- **URL**: `https://jr-finance.fly.dev`
- **Settings**: `config.settings.production` — `DJANGO_SETTINGS_MODULE` seteado como variable de entorno
- **DB**: SQLite en volumen persistente montado en `/data/db.sqlite3`
  - Volumen: `jr_finance_data` (1GB, región `gru`, snapshots automáticos cada 5 días)
  - Sobrevive deploys, reinicios y actualizaciones de la imagen
- **Procesos**: 2 máquinas separadas en el mismo app
  - `web` — gunicorn con 2 workers, puerto 8000
  - `bot` — `python manage.py run_bot` (polling Telegram, siempre activo)

### Secrets configurados

Manejados con `fly secrets set` — nunca van en el repo:

| Secret | Descripción |
|--------|-------------|
| `SECRET_KEY` | Django secret key |
| `ALLOWED_HOSTS` | `jr-finance.fly.dev` |
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram |

### Arquitectura en producción

Un solo VM corre ambos procesos vía `entrypoint.sh`:
1. `python manage.py migrate` — aplica migraciones al arrancar
2. `python manage.py run_bot &` — bot Telegram en background
3. `gunicorn` — web server en primer plano

El volumen `/data` está montado en esta única máquina. `auto_stop_machines = false` y `min_machines_running = 1` para que el bot esté siempre activo.

### Flujo de redeploy (tras cambios en el código)

```bash
fly auth docker
docker buildx build --platform linux/amd64 --push -t registry.fly.io/jr-finance:latest .
fly deploy --image registry.fly.io/jr-finance:latest
```

### Comandos de operación

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

Si la DB en `/data/db.sqlite3` ya existe, hay que borrarla primero:

```bash
fly ssh console -C "rm /data/db.sqlite3"
fly sftp shell
> put db.sqlite3 /data/db.sqlite3
> exit
fly machine restart
```

### Primer deploy / setup inicial

```bash
# 1. Instalar flyctl
brew install flyctl

# 2. Login
fly auth login

# 3. Crear app y volumen
fly apps create jr-finance
fly volumes create jr_finance_data --region gru --size 1

# 4. Configurar secrets
fly secrets set SECRET_KEY="..."
fly secrets set ALLOWED_HOSTS="jr-finance.fly.dev"
fly secrets set TELEGRAM_BOT_TOKEN="..."

# 5. Build y deploy (desde Mac Apple Silicon)
fly auth docker
docker buildx build --platform linux/amd64 --push -t registry.fly.io/jr-finance:latest .
fly deploy --image registry.fly.io/jr-finance:latest

# 6. Subir BD real
fly ssh console -C "python manage.py migrate"

# 8. Escalar bot
fly scale count bot=1
```
