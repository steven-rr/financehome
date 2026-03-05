# FinanceHome

A personal finance management application that connects to your bank accounts via Plaid to provide a unified view of your finances.

## Features

- **Bank Account Syncing** — Link accounts through Plaid for automatic balance and transaction updates
- **Transaction Management** — Browse, search, categorize, and import/export transactions
- **Budgets** — Set and track spending budgets by category
- **AI Insights** — Get AI-powered financial insights and transaction categorization
- **Recurring Transactions** — Automatically detect and track subscriptions and recurring charges
- **Analytics** — Visualize spending patterns and trends
- **Email Digests** — Receive periodic financial summaries via email
- **Data Export** — Export your financial data in CSV format

## Tech Stack

**Frontend:** React 19, TypeScript, Vite, Tailwind CSS v4, React Query v5

**Backend:** FastAPI, SQLAlchemy 2.0, Alembic, Python 3.12

**Database:** Supabase PostgreSQL

**Infrastructure:** Firebase Hosting (frontend), GCP Cloud Run (backend)

**Integrations:** Plaid (bank connectivity), Resend (email)

## Security

- Multi-factor authentication (TOTP)
- Bcrypt password hashing with enforced complexity
- Rate limiting on authentication endpoints
- HTTP security headers (HSTS, CSP, X-Frame-Options, X-Content-Type-Options)
- Audit logging of sensitive actions
- Encrypted data at rest and in transit
- Consent tracking for Plaid data sharing

## Legal

- [Privacy Policy](docs/privacy-policy.md)
- [Terms of Service](docs/terms-of-service.md)

## Contact

steverelativity@gmail.com
