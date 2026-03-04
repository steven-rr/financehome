from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.rate_limit import limiter
from app.routers import accounts, auth, budgets, categorize, csv_import, export, insights, mfa, notifications, plaid, recurring, transactions

app = FastAPI(title="FinanceHome API", version="1.0.0")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(mfa.router, prefix="/api/auth/mfa", tags=["mfa"])
app.include_router(plaid.router, prefix="/api/plaid", tags=["plaid"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(transactions.router, prefix="/api/transactions", tags=["transactions"])
app.include_router(insights.router, prefix="/api/insights", tags=["insights"])
app.include_router(export.router, prefix="/api/export", tags=["export"])
app.include_router(csv_import.router, prefix="/api/import", tags=["import"])
app.include_router(categorize.router, prefix="/api/categorize", tags=["categorize"])
app.include_router(recurring.router, prefix="/api/recurring", tags=["recurring"])
app.include_router(budgets.router, prefix="/api/budgets", tags=["budgets"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
