"""AI features: auto-categorizing transactions and monthly spending insights.

Each feature has two engines:
  * "ai"    - asks Claude (only when ANTHROPIC_API_KEY is set)
  * "rules" - a built-in, offline fallback, so the app always works

If the Claude call fails for any reason (no key, network, rate limit), we fall back to rules.
"""
import json
import logging
import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel

from .config import AI_MODEL, ANTHROPIC_API_KEY

log = logging.getLogger(__name__)

_client = None


def ai_enabled() -> bool:
    return bool(ANTHROPIC_API_KEY)


def _get_client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _ask_claude(system: str, prompt: str, schema: dict, max_tokens: int = 2000) -> dict | None:
    """Sends one request to Claude and returns the JSON it produced, or None on any failure."""
    if not ai_enabled():
        return None
    try:
        response = _get_client().beta.messages.create(
            model=AI_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            # Structured output: Claude must answer with JSON matching our schema
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            # If the request is declined, the API retries it on a fallback model automatically
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason in ("refusal", "max_tokens"):
            log.warning("Claude stopped with %s; using rules instead", response.stop_reason)
            return None
        text = next(b.text for b in response.content if b.type == "text")
        return json.loads(text)
    except Exception as exc:  # any failure -> the rules engine takes over
        log.warning("Claude request failed (%s); using rules instead", exc)
        return None


# ---------------------------------------------------------------------------
# 1. Auto-categorize
# ---------------------------------------------------------------------------

# Keywords for the default categories. Lowercase; matched as whole words or word prefixes.
KEYWORDS = {
    "expense": {
        "Food": ["food", "swiggy", "zomato", "restaurant", "cafe", "coffee", "lunch", "dinner", "breakfast",
                 "grocer", "groceries", "supermarket", "pizza", "burger", "snack", "tea", "bakery", "dominos",
                 "kfc", "mcdonald", "blinkit", "zepto", "bigbasket", "vegetable", "fruit", "milk", "meal"],
        "Rent": ["rent", "landlord", "lease", "pg", "hostel"],
        "Transport": ["uber", "ola", "rapido", "taxi", "cab", "auto", "metro", "bus", "train", "irctc", "petrol",
                      "diesel", "fuel", "parking", "toll", "flight", "airline", "fastag"],
        "Shopping": ["amazon", "flipkart", "myntra", "ajio", "meesho", "shopping", "clothes", "shoes", "shirt",
                     "dress", "mall", "electronics", "gadget", "headphone"],
        "Bills": ["bill", "electricity", "water", "gas", "wifi", "internet", "broadband", "recharge", "mobile",
                  "phone", "airtel", "jio", "insurance", "emi", "loan", "subscription"],
        "Entertainment": ["movie", "cinema", "netflix", "prime", "hotstar", "spotify", "concert", "game",
                          "gaming", "pvr", "inox", "party", "bookmyshow", "youtube"],
        "Health": ["doctor", "hospital", "clinic", "pharmacy", "medicine", "medical", "apollo", "gym",
                   "fitness", "dental", "health", "pharmeasy", "lab", "test"],
    },
    "income": {
        "Salary": ["salary", "payroll", "stipend", "wages", "paycheck", "bonus", "payslip"],
        "Freelance": ["freelance", "client", "project", "invoice", "contract", "consulting", "upwork", "fiverr",
                      "gig"],
        "Gifts": ["gift", "birthday", "present", "cashback", "reward"],
    },
}

WORD = re.compile(r"[a-z0-9]+")
STOPWORDS = {"the", "a", "an", "for", "to", "of", "and", "at", "in", "on", "with", "my", "from", "paid", "payment"}


def _words(text: str) -> set[str]:
    return {w for w in WORD.findall(text.lower()) if w not in STOPWORDS and len(w) > 1}


def categorize_with_rules(note: str, tx_type: str, categories: list[dict], history: list[dict]) -> str | None:
    """Returns a category name or None.

    Order: 1) the user's own past transactions with similar notes (it learns from you),
           2) the category name itself appears in the note,
           3) built-in keyword lists.
    """
    words = _words(note)
    if not words:
        return None
    names = {c["name"] for c in categories}

    # 1) Learn from history: which category did the user pick for notes sharing words with this one?
    votes = Counter()
    for past in history:
        if past["category"] in names:
            overlap = len(words & _words(past["note"]))
            if overlap:
                votes[past["category"]] += overlap
    if votes:
        return votes.most_common(1)[0][0]

    # 2) The note mentions a category by name (works for custom categories too)
    for name in names:
        if _words(name) & words:
            return name

    # 3) Keyword lists
    scores = Counter()
    for name, keywords in KEYWORDS.get(tx_type, {}).items():
        if name not in names:
            continue
        for w in words:
            if any(w == k or (len(k) >= 4 and w.startswith(k)) for k in keywords):
                scores[name] += 1
    if scores:
        return scores.most_common(1)[0][0]
    return None


def categorize_with_ai(note: str, tx_type: str, categories: list[dict], history: list[dict]) -> str | None:
    names = [c["name"] for c in categories]
    examples = "\n".join(f'- "{h["note"]}" -> {h["category"]}' for h in history[:20]) or "(none yet)"
    result = _ask_claude(
        system="You categorize personal finance transactions. Pick the single best category from the list "
               "given. If none fits reasonably, answer null.",
        prompt=f"Transaction type: {tx_type}\nDescription: {note}\n\nAllowed categories: {', '.join(names)}\n\n"
               f"How this user categorized past transactions:\n{examples}",
        schema={
            "type": "object",
            "properties": {"category": {"anyOf": [{"type": "string", "enum": names}, {"type": "null"}]}},
            "required": ["category"],
            "additionalProperties": False,
        },
        max_tokens=1000,
    )
    if result is None:
        return None
    category = result.get("category")
    return category if category in names else ""  # "" means Claude answered but found no fit


def suggest_category(note: str, tx_type: str, categories: list[dict], history: list[dict]) -> tuple[str | None, str]:
    """Returns (category name or None, engine used)."""
    if ai_enabled():
        name = categorize_with_ai(note, tx_type, categories, history)
        if name is not None:
            return (name or None), "ai"
    return categorize_with_rules(note, tx_type, categories, history), "rules"


# ---------------------------------------------------------------------------
# 2. Monthly insights
# ---------------------------------------------------------------------------

class Insight(BaseModel):
    kind: Literal["positive", "warning", "info", "tip"]
    title: str
    text: str


def _money(value: float) -> str:
    return f"₹{value:,.0f}"


def insights_with_rules(stats: dict) -> tuple[str, list[Insight]]:
    cur, prev = stats["current"], stats["previous"]
    out: list[Insight] = []

    if cur["income"] == 0 and cur["expenses"] == 0:
        return "No transactions this month yet.", [
            Insight(kind="tip", title="Start tracking", text="Add your income and expenses to get insights here.")
        ]

    # Savings rate
    rate = cur["savings_rate"]
    if cur["income"] > 0:
        if rate >= 20:
            out.append(Insight(kind="positive", title="Healthy savings",
                               text=f"You saved {rate:.0f}% of your income this month. Keep it up!"))
        elif rate >= 0:
            out.append(Insight(kind="tip", title="Room to save more",
                               text=f"You saved {rate:.0f}% of your income. A common target is 20%, which would be "
                                    f"{_money(cur['income'] * 0.2)}."))
        else:
            out.append(Insight(kind="warning", title="Spending more than you earn",
                               text=f"Expenses are {_money(cur['expenses'] - cur['income'])} above income this month."))

    # Overall change vs last month
    if prev["expenses"] > 0:
        change = (cur["expenses"] - prev["expenses"]) / prev["expenses"] * 100
        if change >= 10:
            out.append(Insight(kind="warning", title="Spending is up",
                               text=f"You spent {change:.0f}% more than last month "
                                    f"({_money(cur['expenses'])} vs {_money(prev['expenses'])})."))
        elif change <= -10:
            out.append(Insight(kind="positive", title="Spending is down",
                               text=f"You spent {abs(change):.0f}% less than last month. Nice work!"))

    # Biggest category movers
    prev_cats = prev["by_category"]
    movers = []
    for name, amount in cur["by_category"].items():
        before = prev_cats.get(name, 0)
        if before > 0 and amount - before >= max(500, before * 0.25):
            movers.append((amount - before, name, before, amount))
    for diff, name, before, amount in sorted(movers, reverse=True)[:2]:
        out.append(Insight(kind="info", title=f"{name} went up",
                           text=f"{name} rose by {_money(diff)} ({_money(before)} → {_money(amount)})."))

    # Top category share
    if cur["by_category"] and cur["expenses"] > 0:
        top, amount = max(cur["by_category"].items(), key=lambda kv: kv[1])
        share = amount / cur["expenses"] * 100
        out.append(Insight(kind="info", title=f"Top category: {top}",
                           text=f"{top} is {share:.0f}% of your spending ({_money(amount)})."))

    # Budgets
    for b in stats["budgets"]:
        if b["status"] == "over":
            over = b["spent"] - b["limit"]
            used = f"You're {_money(over)} over your" if over >= 1 else "You've used all of your"
            out.append(Insight(kind="warning", title=f"{b['category']} budget " + ("exceeded" if over >= 1 else "used up"),
                               text=f"{used} {b['category']} budget. "
                                    f"Try pausing non-essential {b['category'].lower()} spending for the rest of the month."))
        elif b["status"] == "warning" and stats["days_left"] > 0:
            left = b["limit"] - b["spent"]
            out.append(Insight(kind="tip", title=f"Watch your {b['category']} budget",
                               text=f"{_money(left)} left for {stats['days_left']} days, about "
                                    f"{_money(left / stats['days_left'])} a day."))

    # Goals
    for g in stats["goals"]:
        if g["monthly_needed"] and cur["income"] > 0 and cur["income"] - cur["expenses"] < g["monthly_needed"]:
            out.append(Insight(kind="tip", title=f"Goal: {g['name']}",
                               text=f"You need about {_money(g['monthly_needed'])} a month for this goal, but saved "
                                    f"{_money(max(cur['income'] - cur['expenses'], 0))} this month."))

    summary = (f"You earned {_money(cur['income'])} and spent {_money(cur['expenses'])} this month"
               + (f", saving {rate:.0f}% of your income." if cur["income"] > 0 else "."))
    return summary, out[:6]


INSIGHTS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "insights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["positive", "warning", "info", "tip"]},
                    "title": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["kind", "title", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "insights"],
    "additionalProperties": False,
}


def insights_with_ai(stats: dict) -> tuple[str, list[Insight]] | None:
    result = _ask_claude(
        system=(
            "You are a friendly personal finance assistant inside a budgeting app. Given one month of a user's "
            "data, write a one or two sentence summary and 3 to 5 short insights. Each insight is a concrete "
            "observation or a practical, specific tip based only on the numbers given (spending changes, "
            "budgets, savings rate, goals). Amounts are in Indian rupees; write them like ₹1,200. Keep each "
            "insight text under 35 words. Use kind 'warning' for problems, 'positive' for good news, 'tip' "
            "for advice and 'info' for neutral observations. Do not invent data."
        ),
        prompt="Here is the data as JSON:\n" + json.dumps(stats, indent=1),
        schema=INSIGHTS_SCHEMA,
    )
    if result is None:
        return None
    try:
        insights = [Insight(**i) for i in result["insights"]][:6]
        return result["summary"], insights
    except Exception:
        return None


# Cache AI insights so reloading the dashboard doesn't call the API again unless the data changed.
_insight_cache: dict[tuple, tuple[str, list[Insight]]] = {}


def monthly_insights(user_id: int, stats: dict) -> tuple[str, list[Insight], str]:
    """Returns (summary, insights, engine used)."""
    if ai_enabled():
        key = (user_id, json.dumps(stats, sort_keys=True))
        if key in _insight_cache:
            return (*_insight_cache[key], "ai")
        ai = insights_with_ai(stats)
        if ai is not None:
            if len(_insight_cache) > 500:
                _insight_cache.clear()
            _insight_cache[key] = ai
            return (*ai, "ai")
    return (*insights_with_rules(stats), "rules")
