# Finance

Control de finanzas personales en COP y USD. Gestiona cuentas de ahorro, gastos fijos mensuales e ingresos/egresos. El usuario administra todo desde el Django Admin y registra transacciones vía Telegram.

## Models

### UserProfile (UUID ID)
Extiende `auth.User` vía OneToOne. Agrega `phone_number` y `telegram_chat_id` (único, nullable) para identificar al usuario en canales de mensajería.

### Account (UUID ID)
Cuenta del usuario con `balance` (se actualiza automáticamente en cada transacción), `currency` (COP/USD) y `name`. Un usuario puede tener múltiples cuentas en distintas monedas.

### MonthlyExpense (UUID ID)
Gasto fijo mensual con FK a `Account` (de qué cuenta sale el dinero). No tiene campo `currency` propio — se hereda de `account.currency`. Se usa para calcular el ahorro mínimo mensual.

### Transaction (UUID ID)
Ingreso o egreso vinculado a una `Account`. Al crearse vía `TransactionService.create()`, actualiza automáticamente `account.balance`. El campo `created_via` registra si fue creada desde `admin` o `telegram`.

## Business Rules

- El balance de `Account` se actualiza en `TransactionService.create()`: income suma, expense resta. La actualización es directa sobre `account.balance` + `account.save()`, no pasa por `AccountSelector.update()`.
- `MonthlyExpense` hereda la moneda de su `Account` — no tiene campo `currency` propio.
- El ahorro mínimo objetivo es el **35%** de los ingresos del mes (`FinanceSummaryService.SAVINGS_TARGET = 0.35`).
- El resumen mensual (`FinanceSummaryService.get_monthly_summary()`) calcula ingresos, egresos, gastos fijos y ahorro separados por moneda (COP/USD), nunca los mezcla.
- Solo usuarios con `telegram_chat_id` registrado en `UserProfile` pueden usar el bot.

## Error Codes (`F` prefix)

| Code | HTTP | Description |
|------|------|-------------|
| F01 | 404 | Perfil de usuario no encontrado |
| F02 | 404 | Cuenta no encontrada |
| F03 | 404 | Transacción no encontrada |
| F04 | 404 | Gasto mensual no encontrado |
| F05 | 400 | La cuenta no pertenece al usuario |

## API Endpoints

Todos requieren `Authorization: Api-Key <key>`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/profiles/{uuid}/summary/` | Usuario + cuentas + gastos fijos + resumen mensual actual |
| GET | `/api/v1/profiles/{uuid}/accounts/` | Cuentas del usuario |
| GET | `/api/v1/profiles/{uuid}/transactions/` | Historial de transacciones |
| POST | `/api/v1/profiles/{uuid}/transactions/` | Registrar ingreso o egreso |

## Dependencies

- `auth.User` (Django built-in) — base del `UserProfile`
- `utils.channels.telegram` — accede a `UserProfile` y llama a `TransactionService` y `FinanceSummaryService`

## Notes

- `FinanceSummaryService` no es subclase de `BaseService` — es un servicio de solo lectura sin CRUD.
- Al agregar nuevos canales (WhatsApp, Twilio), seguir el mismo patrón de `utils/channels/telegram/`: un `db.py` con funciones síncronas y handlers que las envuelven con `sync_to_async`.
