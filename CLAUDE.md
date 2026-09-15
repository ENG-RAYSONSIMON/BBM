# Beauty Business Manager (BBM)

Multi-tenant SaaS for Tanzanian cosmetics/beauty retailers. Owners and Admin
staff manage products, stock, sales, purchases, expenses, and profit
reporting — entirely scoped per business (tenant).

## Stack
- Backend: Django REST Framework, PostgreSQL 15+ (UUID PKs), Redis,
  Celery (deferred to Phase 4), Argon2 password hashing, JWT via SimpleJWT
  with refresh rotation, drf-spectacular for OpenAPI docs.
- Frontend: React (Vite), TypeScript, Tailwind, shadcn/ui, TanStack Query,
  React Hook Form, Zod, Recharts. (not started yet)
- Infra: Docker Compose (db, redis, backend, frontend, nginx).

## Non-negotiable architecture rules
Full detail in docs/BBM_SRS_Summary_Draft.pdf. Summary:
- Every tenant-owned table carries `business_id`, derived from the JWT —
  never from a client-supplied field. Enforce scoping centrally (a shared
  manager/queryset), not per-view.
- Stock is never edited directly. Every change is a `stock_movements`
  ledger row; current stock is a derived sum.
- `sale_items` / `purchase_items` snapshot unit price and cost at
  transaction time. Product price changes must never rewrite historical
  profit.
- The sale transaction (validate stock → create sale+items → decrement
  stock → write stock movement → compute COGS/profit → record payment)
  runs in one atomic DB transaction with full rollback on any failure.

## Working conventions
- Plan before writing code — propose an approach, wait for my approval,
  then implement.
- Keep changes scoped to what was asked; don't refactor unrelated code.
- Never put real secrets in code or migrations — use REPLACE_ME
  placeholders and tell me where to fill them in.
- After implementing, tell me what to test and how before I commit.