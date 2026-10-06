---
paths:
  - "frontend/**"
---

# Frontend rules (React / Vite / TypeScript)

Commands (run in `frontend/`): `npm test` (Vitest), `npm run lint` (oxlint),
`npm run typecheck`, `npm run build`.

## Data and API
- All HTTP goes through `api()` in `src/lib/api.ts` — it handles the in-memory
  access token, refresh rotation on 401, and `ApiError`. Don't call `fetch`
  directly and don't store the access token anywhere.
- Server state uses TanStack Query. Query keys start with the resource name
  (`['products', page, search, filters]`); invalidate by that prefix after
  mutations. Use `placeholderData: (prev) => prev` on paginated lists.
- API response types live in `src/lib/types.ts` (`Paginated<T>`, etc.) and must
  match the DRF serializers. Money arrives as decimal strings — format with
  `formatTZS` from `src/lib/format.ts`, never `parseFloat` for arithmetic.
- Never send `business_id` in a request body or query; the token selects it.

## Forms
- React Hook Form + Zod. Schemas live in `src/lib/schemas.ts`.
- Map server errors with `applyServerErrors(error, setError, fields)` from
  `src/lib/forms.ts`; render `root.server` with `FormError`.

## Pages and UI
- List pages: `useListParams()` (state in the URL), `DataList` for
  loading/empty/error/pagination, `PageHeader`, `SearchInput`, `RefSelect`.
  Copy the shape of `src/pages/products.tsx`.
- Gate actions and nav with `useAuth().can(PERMISSIONS.x)`; the backend still
  enforces, this is only UX.
- shadcn/ui primitives in `src/components/ui/` — add new ones with the shadcn
  CLI, don't hand-roll. Icons from `lucide-react`. Tailwind v4 only.
- Use `ConfirmDialog`, not `window.confirm`. Toasts via `sonner`.
- Must work on mobile (tables collapse to cards) and in dark mode.
- Imports use the `@/` alias.

## Tests
- Vitest + Testing Library. Stub the network with `mockFetch()` from
  `src/test/fetch-mock.ts` (keys like `'GET /products/'`), render with
  `renderRoute()` or `renderWithAuth(path, routes, permissions)` from
  `src/test/render.tsx`, and reuse `src/test/fixtures.ts`.
- New pages get tests for loading/empty/error states, permission gating, and
  server validation errors on forms.
