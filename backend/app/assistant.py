"""The in-app AI assistant: a chat that answers questions about the user's money and about the app.

How it stays private:
  * The model runs locally through Ollama, so nothing leaves the computer.
  * The model never sees the database. It can only call the read-only "tools" below, and every tool is
    bound to the logged-in user's id on the server. The model can't pass a user id, so it can't ask for
    anyone else's data.
  * The chat history sent by the browser may only contain "user" and "assistant" messages, so a client
    can't inject its own system prompt or fake tool results.

Flow for one question:
  1. Build a system prompt: how the app works, today's date, and a short snapshot of this month.
  2. Ask the model. If it calls tools, run them for this user and send the results back. Repeat (max a
     few rounds).
  3. Stream the final answer back to the browser, token by token.
"""
import json
import logging
from collections.abc import Iterator
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models, ollama
from .routers.dashboard import shift_month, totals
from .services import budget_out, goal_out, month_bounds

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4
MAX_HISTORY = 12  # most recent chat messages sent to the model

APP_GUIDE = """\
About the app ("Finance", a personal finance tracker). Amounts are Indian rupees (₹).
Pages (top bar on desktop, tab bar at the bottom on phones):
- Dashboard: this month's income, expenses, balance and savings rate; a donut chart of spending by
  category; a 6 month income vs expenses trend; budget alerts; and "Monthly insights" with tips.
- Transactions: every income and expense. "+ Add" opens a form with amount, type (expense or income),
  date, category and description. Typing a description auto-suggests a category. Filter by month, type
  and category or search descriptions. Hover a row (or tap it on a phone) to edit or delete it.
  Buttons at the top: "New category" (add your own category), "Export" (download a CSV of the current
  filter), "Scan receipt" (upload a JPG/PNG/WebP receipt; the merchant, total and date are read and
  filled in for you to check and save), "Import GPay" (upload a Google Pay statement PDF) and
  "Import bank" (upload a statement from any bank as PDF, Excel, CSV or text; password-protected PDFs
  work too). Imports show a review screen first where you can untick rows and change categories, and
  rows already imported are skipped automatically.
- Analytics: pick a range of months to see totals, average monthly spending, a monthly chart, spending
  by category and your biggest expense.
- Budgets: set a monthly spending limit per expense category with "Add". A budget turns amber at 80%
  and red when you go over. Each month has its own budgets.
- Goals: "New goal" creates a savings goal with a target and an optional deadline. "Add money" records
  money saved towards it. The app shows progress and how much to save each month to finish on time.
- Account: sign up with name, email and password; log out with the button at the top right. Each
  account only ever sees its own data.
- AI: auto-categorize, monthly insights and this assistant all run on a local AI model through Ollama.
"""

SYSTEM_PROMPT = """\
You are the assistant inside a personal finance app. You help {name} understand their own money and
how to use the app. Today is {today}.

Rules:
- For questions about their money, get the numbers from the tools. Never guess or invent amounts,
  dates, merchants or transactions. If the tools return nothing, say so.
- Write amounts like ₹1,250. Keep answers short and friendly: a sentence or two, or a short list.
- You can only read data. You can't add, edit or delete anything; if asked, explain where in the app
  to do it.
- For dates: "this month" is {this_month}, "last month" is {last_month}. Use YYYY-MM-DD dates in tool
  calls.
- Only talk about personal finance and this app. Politely decline anything unrelated.

{guide}
Snapshot of {this_month} (use the tools for anything else):
{snapshot}
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_summary",
            "description": "Total income, total expenses, balance, savings rate and spending per category "
                           "for a date range. Defaults to the current month.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "First day, YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "Last day (inclusive), YYYY-MM-DD"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_transactions",
            "description": "Find the user's transactions. Returns matching rows plus their count and total. "
                           "Use it for questions like 'how much did I spend on Swiggy', 'my biggest expenses' "
                           "or 'what did I buy last week'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Word to look for in the description, e.g. a merchant"},
                    "category": {"type": "string", "description": "Category name, e.g. Food"},
                    "type": {"type": "string", "enum": ["expense", "income"]},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive"},
                    "min_amount": {"type": "number"},
                    "sort": {"type": "string", "enum": ["newest", "largest"]},
                    "limit": {"type": "integer", "description": "Max rows to list (default 15, max 50)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_monthly_trend",
            "description": "Income and expenses for each of the last N months, oldest first.",
            "parameters": {
                "type": "object",
                "properties": {"months": {"type": "integer", "description": "How many months (1 to 24, default 6)"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_budgets",
            "description": "The user's budgets for a month with limit, amount spent, percent used and status.",
            "parameters": {
                "type": "object",
                "properties": {"month": {"type": "string", "description": "YYYY-MM, default the current month"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_goals",
            "description": "The user's savings goals with target, saved amount, progress, deadline and how much "
                           "to save per month.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_categories",
            "description": "The user's income and expense category names.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

STATUS_TEXT = {
    "get_summary": "Adding up your totals…",
    "search_transactions": "Searching your transactions…",
    "get_monthly_trend": "Looking at your monthly trend…",
    "get_budgets": "Checking your budgets…",
    "get_goals": "Checking your goals…",
    "list_categories": "Looking at your categories…",
}


def _date(value, default: date) -> date:
    if not value:
        return default
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ValueError(f"Invalid date '{value}', use YYYY-MM-DD")


def _month(value, default: str) -> str:
    value = str(value or default)[:7]
    try:
        date.fromisoformat(value + "-01")
    except ValueError:
        raise ValueError(f"Invalid month '{value}', use YYYY-MM")
    return value


class UserTools:
    """Read-only tools for ONE user. Every query below filters on self.user_id."""

    def __init__(self, db: Session, user: models.User, today: date | None = None):
        self.db = db
        self.user_id = user.id
        self.today = today or date.today()

    def run(self, name: str, args) -> dict:
        if not isinstance(args, dict):
            try:
                args = json.loads(args or "{}")
            except (TypeError, ValueError):
                args = {}
        method = getattr(self, name, None) if name in STATUS_TEXT else None
        if method is None:
            return {"error": f"Unknown tool '{name}'"}
        try:
            return method(**{k: v for k, v in args.items() if v not in (None, "")})
        except TypeError as exc:
            return {"error": f"Bad arguments: {exc}"}
        except ValueError as exc:
            return {"error": str(exc)}

    # --- tools ---------------------------------------------------------------------------------

    def get_summary(self, start_date=None, end_date=None, **_):
        start = _date(start_date, self.today.replace(day=1))
        end = _date(end_date, month_bounds(self.today.strftime("%Y-%m"))[1] - timedelta(days=1))
        rows = self.db.execute(
            select(models.Transaction.type, models.Category.name, func.sum(models.Transaction.amount),
                   func.count(models.Transaction.id))
            .join(models.Category, models.Transaction.category_id == models.Category.id)
            .where(models.Transaction.user_id == self.user_id,
                   models.Transaction.date >= start, models.Transaction.date <= end)
            .group_by(models.Transaction.type, models.Category.name)
        ).all()
        income = sum(float(total) for t, _, total, _ in rows if t == "income")
        expenses = sum(float(total) for t, _, total, _ in rows if t == "expense")
        by_category = sorted(((name, float(total)) for t, name, total, _ in rows if t == "expense"),
                             key=lambda r: -r[1])
        return {
            "start_date": str(start),
            "end_date": str(end),
            "income": round(income, 2),
            "expenses": round(expenses, 2),
            "balance": round(income - expenses, 2),
            "savings_rate_percent": round((income - expenses) / income * 100, 1) if income else None,
            "transaction_count": sum(int(n) for *_, n in rows),
            "spending_by_category": {name: round(total, 2) for name, total in by_category},
            "income_by_category": {name: round(float(total), 2) for t, name, total, _ in rows if t == "income"},
        }

    def search_transactions(self, text=None, category=None, type=None, start_date=None, end_date=None,
                            min_amount=None, sort="newest", limit=15, **_):
        query = (select(models.Transaction, models.Category.name)
                 .join(models.Category, models.Transaction.category_id == models.Category.id)
                 .where(models.Transaction.user_id == self.user_id))
        if text:
            query = query.where(models.Transaction.note.ilike(f"%{text}%"))
        if category:
            query = query.where(func.lower(models.Category.name) == str(category).lower())
        if type in ("income", "expense"):
            query = query.where(models.Transaction.type == type)
        if start_date:
            query = query.where(models.Transaction.date >= _date(start_date, self.today))
        if end_date:
            query = query.where(models.Transaction.date <= _date(end_date, self.today))
        if min_amount:
            query = query.where(models.Transaction.amount >= float(min_amount))

        matches = query.subquery()
        count, total = self.db.execute(select(func.count(), func.coalesce(func.sum(matches.c.amount), 0))).one()
        order = ((models.Transaction.amount.desc(), models.Transaction.date.desc()) if sort == "largest"
                 else (models.Transaction.date.desc(), models.Transaction.id.desc()))
        limit = max(1, min(int(limit or 15), 50))
        rows = self.db.execute(query.order_by(*order).limit(limit)).all()
        return {
            "match_count": int(count),
            "total_amount": round(float(total), 2),
            "showing": len(rows),
            "transactions": [
                {"date": str(t.date), "type": t.type, "amount": round(t.amount, 2), "category": cat,
                 "description": t.note}
                for t, cat in rows
            ],
        }

    def get_monthly_trend(self, months=6, **_):
        months = max(1, min(int(months or 6), 24))
        end = self.today.strftime("%Y-%m")
        out = []
        for offset in range(months - 1, -1, -1):
            m = shift_month(end, -offset)
            income, expenses = totals(self.db, self.user_id, m)
            out.append({"month": m, "income": income, "expenses": expenses, "saved": round(income - expenses, 2)})
        return {"months": out}

    def get_budgets(self, month=None, **_):
        month = _month(month, self.today.strftime("%Y-%m"))
        budgets = self.db.scalars(select(models.Budget).where(
            models.Budget.user_id == self.user_id, models.Budget.month == month)).all()
        return {
            "month": month,
            "budgets": [
                {"category": b.category.name, "limit": b.limit, "spent": b.spent, "left": round(b.limit - b.spent, 2),
                 "percent_used": b.percent, "status": b.status}
                for b in (budget_out(self.db, b) for b in budgets)
            ],
        }

    def get_goals(self, **_):
        goals = self.db.scalars(select(models.Goal).where(models.Goal.user_id == self.user_id)).all()
        return {
            "goals": [
                {"name": g.name, "target": g.target_amount, "saved": g.saved_amount, "remaining": g.remaining,
                 "percent": g.percent, "deadline": str(g.deadline) if g.deadline else None,
                 "save_per_month_to_finish": g.monthly_needed, "completed": g.completed}
                for g in (goal_out(g, self.today) for g in goals)
            ],
        }

    def list_categories(self, **_):
        cats = self.db.scalars(select(models.Category).where(models.Category.user_id == self.user_id)).all()
        return {t: sorted(c.name for c in cats if c.type == t) for t in ("expense", "income")}

    # --- context for the system prompt ---------------------------------------------------------

    def snapshot(self) -> str:
        summary = self.get_summary()
        data = {
            "income": summary["income"],
            "expenses": summary["expenses"],
            "balance": summary["balance"],
            "spending_by_category": summary["spending_by_category"],
            "budgets": self.get_budgets()["budgets"],
            "goals": self.get_goals()["goals"],
            "recent_transactions": self.search_transactions(limit=5)["transactions"],
        }
        return json.dumps(data, ensure_ascii=False)


def build_system_prompt(tools: UserTools, user: models.User) -> str:
    this_month = tools.today.strftime("%Y-%m")
    return SYSTEM_PROMPT.format(
        name=(user.name or "the user").split()[0],
        today=tools.today.strftime("%A, %d %B %Y"),
        this_month=this_month,
        last_month=shift_month(this_month, -1),
        guide=APP_GUIDE,
        snapshot=tools.snapshot(),
    )


def _event(kind: str, **data) -> str:
    return json.dumps({"type": kind, **data}, ensure_ascii=False) + "\n"


def chat(db: Session, user: models.User, history: list[dict], today: date | None = None) -> Iterator[str]:
    """Runs one assistant turn. Yields newline-delimited JSON events for the browser:

    {"type": "status", "text": "Searching your transactions…"}   while a tool runs
    {"type": "token", "text": "You spent "}                        pieces of the answer
    {"type": "error", "text": "...", "code": "unavailable"}        something went wrong
    {"type": "done"}                                               finished
    """
    tools = UserTools(db, user, today)
    messages = [{"role": "system", "content": build_system_prompt(tools, user)}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history[-MAX_HISTORY:]]
    use_tools = True

    try:
        for _round in range(MAX_TOOL_ROUNDS + 1):
            content, calls = "", []
            try:
                # On the last round, no tools: the model has to answer with what it has
                offer = TOOLS if use_tools and _round < MAX_TOOL_ROUNDS else None
                for chunk in ollama.chat_stream(messages, tools=offer):
                    if chunk.get("tool_calls"):
                        calls += chunk["tool_calls"]
                    piece = chunk.get("content") or ""
                    if piece:
                        content += piece
                        if not calls:
                            yield _event("token", text=piece)
            except ollama.ToolsUnsupported:
                # Some models can't call tools. They still get the snapshot in the system prompt.
                log.info("Model %s doesn't support tools; answering from the snapshot", ollama.config.OLLAMA_MODEL)
                use_tools = False
                continue

            if not calls:
                if not content.strip():
                    yield _event("token", text="Sorry, I couldn't come up with an answer. Could you rephrase that?")
                yield _event("done")
                return

            messages.append({"role": "assistant", "content": content, "tool_calls": calls})
            for call in calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                yield _event("status", text=STATUS_TEXT.get(name, "Looking that up…"))
                result = tools.run(name, fn.get("arguments") or {})
                messages.append({"role": "tool", "tool_name": name, "content": json.dumps(result, ensure_ascii=False)})
    except ollama.OllamaUnavailable as exc:
        yield _event("error", text=str(exc), code="unavailable")
    except ollama.ModelMissing as exc:
        yield _event("error", text=str(exc), code="model_missing")
    except ollama.OllamaError as exc:
        yield _event("error", text=str(exc), code="error")
    except Exception:  # never leave the browser hanging
        log.exception("Assistant failed")
        yield _event("error", text="Something went wrong while answering. Please try again.", code="error")
    yield _event("done")
