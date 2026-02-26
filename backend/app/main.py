from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import accounts, auth, insights, plaid, transactions

app = FastAPI(title="FinanceHome API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(plaid.router, prefix="/api/plaid", tags=["plaid"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(transactions.router, prefix="/api/transactions", tags=["transactions"])
app.include_router(insights.router, prefix="/api/insights", tags=["insights"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
