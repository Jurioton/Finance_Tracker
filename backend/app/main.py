from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGIN_REGEX, CORS_ORIGINS
from .database import Base, add_missing_columns, engine
from .routers import ai, auth, budgets, categories, dashboard, goals, receipts, statements, transactions

# Creates the SQLite tables on startup if they don't exist yet.
Base.metadata.create_all(bind=engine)
add_missing_columns(engine)

app = FastAPI(
    title="Personal Finance Tracker API",
    description="Record income and expenses, set budgets, view spending patterns and track savings goals.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (auth.router, categories.router, transactions.router, budgets.router, goals.router, dashboard.router, ai.router, receipts.router,
               statements.router):
    app.include_router(router)


@app.get("/", tags=["health"])
def health():
    return {"status": "ok"}
