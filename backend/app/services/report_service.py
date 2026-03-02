import calendar
import io
import json
import uuid
from collections import defaultdict
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import Budget
from app.services.analytics_service import (
    CREDIT_CARD_PAYMENT_PATTERNS,
    TRANSFER_CATEGORIES,
    AnalyticsService,
)
from app.services.claude_service import InsightsService
from app.services.recurring_service import RecurringService

EMERALD = colors.HexColor("#059669")
EMERALD_LIGHT = colors.HexColor("#d1fae5")
SLATE_700 = colors.HexColor("#334155")
SLATE_100 = colors.HexColor("#f1f5f9")

analytics = AnalyticsService()
recurring_svc = RecurringService()
ai_service = InsightsService()

FREQ_MULTIPLIERS = {"weekly": 4.33, "bi-weekly": 2.17, "monthly": 1.0, "quarterly": 0.33, "annual": 0.083}


def _is_transfer_or_cc_payment(txn: dict) -> bool:
    cat = txn.get("category", "")
    if cat in TRANSFER_CATEGORIES:
        return True
    desc = (txn.get("description") or "").upper()
    merchant = (txn.get("merchant") or "").upper()
    for pattern in CREDIT_CARD_PAYMENT_PATTERNS:
        p = pattern.upper()
        if p in desc or p in merchant:
            return True
    return False


def _truncate(text: str, max_len: int = 40) -> str:
    return text[:max_len - 1] + "\u2026" if len(text) > max_len else text


def _currency(val: float) -> str:
    return f"${val:,.2f}"


def _pct(val: float) -> str:
    return f"{val:.1f}%"


def _change_str(current: float, previous: float) -> str:
    if previous == 0:
        return "N/A"
    change = ((current - previous) / previous) * 100
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.1f}%"


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "ReportTitle", parent=styles["Title"],
        fontSize=22, textColor=SLATE_700, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        "ReportSubtitle", parent=styles["Normal"],
        fontSize=10, textColor=colors.gray, spaceAfter=20,
    ))
    styles.add(ParagraphStyle(
        "SectionHeader", parent=styles["Heading2"],
        fontSize=14, textColor=EMERALD, spaceBefore=18, spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=9, textColor=SLATE_700, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        "BulletText", parent=styles["Normal"],
        fontSize=9, textColor=SLATE_700, spaceAfter=3,
        leftIndent=12,
    ))
    return styles


def _make_table(headers: list[str], rows: list[list], col_widths=None) -> Table:
    data = [headers] + rows
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), EMERALD),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
    ])
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.add("BACKGROUND", (0, i), (-1, i), SLATE_100)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(style)
    return t


def _summary_table(data: list[list]) -> Table:
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), EMERALD),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
    ])
    t = Table(data)
    t.setStyle(style)
    return t


async def _get_budgets(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Budget).where(Budget.user_id == user_id).order_by(Budget.category)
    )
    return [{"category": b.category, "monthly_limit": b.monthly_limit} for b in result.scalars().all()]


def _top_merchants(transactions: list[dict]) -> list[tuple[str, dict]]:
    totals: dict[str, dict] = {}
    for t in transactions:
        if t["amount"] > 0 and not _is_transfer_or_cc_payment(t):
            name = _truncate(t["merchant"] or t["description"] or "Unknown")
            if name in totals:
                totals[name]["total"] += t["amount"]
                totals[name]["count"] += 1
            else:
                totals[name] = {"total": t["amount"], "count": 1}
    return sorted(totals.items(), key=lambda x: x[1]["total"], reverse=True)[:10]


def _income_sources(transactions: list[dict]) -> list[tuple[str, dict]]:
    sources: dict[str, dict] = {}
    for t in transactions:
        if t["amount"] < 0 and not _is_transfer_or_cc_payment(t):
            name = _truncate(t["merchant"] or t["description"] or "Unknown")
            amt = abs(t["amount"])
            if name in sources:
                sources[name]["total"] += amt
                sources[name]["count"] += 1
            else:
                sources[name] = {"total": amt, "count": 1}
    return sorted(sources.items(), key=lambda x: x[1]["total"], reverse=True)


def _largest_expenses(transactions: list[dict], n: int = 5) -> list[dict]:
    expenses = [t for t in transactions if t["amount"] > 0 and not _is_transfer_or_cc_payment(t)]
    expenses.sort(key=lambda t: t["amount"], reverse=True)
    return expenses[:n]


def _daily_spending(transactions: list[dict]) -> dict[str, float]:
    daily: dict[str, float] = defaultdict(float)
    for t in transactions:
        if t["amount"] > 0 and not _is_transfer_or_cc_payment(t):
            daily[t["date"]] += t["amount"]
    return dict(daily)


# ── Section builders ──────────────────────────────────────────────────────────


def _add_comparison(story, styles, current_ie, prev_ie, cur_label, prev_label):
    story.append(Paragraph(f"Comparison: {cur_label} vs {prev_label}", styles["SectionHeader"]))
    rows = [
        ["", prev_label, cur_label, "Change"],
        ["Income", _currency(prev_ie["income"]), _currency(current_ie["income"]),
         _change_str(current_ie["income"], prev_ie["income"])],
        ["Expenses", _currency(prev_ie["expenses"]), _currency(current_ie["expenses"]),
         _change_str(current_ie["expenses"], prev_ie["expenses"])],
        ["Net Savings", _currency(prev_ie["net"]), _currency(current_ie["net"]),
         _change_str(current_ie["net"], prev_ie["net"]) if prev_ie["net"] != 0 else "N/A"],
    ]
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), EMERALD),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
    ])
    t = Table(rows, colWidths=[1.5 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch])
    t.setStyle(style)
    story.append(t)


def _add_daily_avg(story, styles, expenses, num_days, transactions):
    daily_avg = round(expenses / num_days, 2) if num_days > 0 else 0
    daily = _daily_spending(transactions)
    story.append(Paragraph("Daily Spending", styles["SectionHeader"]))
    if daily:
        peak_day = max(daily, key=daily.get)
        data = [
            ["Daily Average", "Highest Spending Day", "That Day's Spend"],
            [_currency(daily_avg), peak_day, _currency(daily[peak_day])],
        ]
    else:
        data = [["Daily Average"], [_currency(daily_avg)]]
    story.append(_summary_table(data))


def _add_income_sources(story, styles, transactions):
    sources = _income_sources(transactions)
    if not sources:
        return
    story.append(Paragraph("Income Sources", styles["SectionHeader"]))
    rows = [[name, _currency(info["total"]), str(info["count"])] for name, info in sources]
    story.append(_make_table(
        ["Source", "Total", "Deposits"],
        rows, col_widths=[3 * inch, 1.5 * inch, 1.5 * inch],
    ))


def _add_largest_expenses(story, styles, transactions):
    largest = _largest_expenses(transactions)
    if not largest:
        return
    story.append(Paragraph("Largest Expenses", styles["SectionHeader"]))
    rows = [
        [_truncate(t["merchant"] or t["description"] or "Unknown"),
         _currency(t["amount"]), t["date"], t["category"]]
        for t in largest
    ]
    story.append(_make_table(
        ["Merchant", "Amount", "Date", "Category"],
        rows, col_widths=[2.5 * inch, 1.2 * inch, 1.2 * inch, 1.5 * inch],
    ))


def _add_recurring(story, styles, recurring_data):
    items = recurring_data.get("items", [])
    if not items:
        return
    total_monthly = recurring_data.get("total_monthly_cost", 0)
    story.append(Paragraph("Recurring & Subscriptions", styles["SectionHeader"]))
    story.append(Paragraph(
        f"Total monthly recurring cost: <b>{_currency(total_monthly)}</b> "
        f"({_currency(total_monthly * 12)}/year)", styles["Body"],
    ))
    rows = []
    for item in sorted(items, key=lambda x: x["amount"] * FREQ_MULTIPLIERS.get(x["frequency"], 1), reverse=True):
        monthly = item["amount"] * FREQ_MULTIPLIERS.get(item["frequency"], 1)
        rows.append([
            _truncate(item["merchant"]),
            _currency(item["amount"]),
            item["frequency"].capitalize(),
            _currency(monthly),
            item["category"],
        ])
    story.append(_make_table(
        ["Merchant", "Amount", "Frequency", "Monthly Equiv.", "Category"],
        rows, col_widths=[1.8 * inch, 1 * inch, 1 * inch, 1.2 * inch, 1.4 * inch],
    ))


async def _generate_ai_insights(
    period_label: str,
    income_expenses: dict,
    categories: list[dict],
    top_merchants: list[tuple[str, dict]],
    prev_ie: dict,
    recurring_data: dict,
    budgets: list[dict],
    daily_avg: float,
) -> list[str]:
    """Call Gemini to generate ~20 bullet-point insights about the financial data."""
    cat_spending = {c["category"]: c["total"] for c in categories}
    budget_status = []
    for b in budgets:
        actual = cat_spending.get(b["category"], 0)
        budget_status.append(f"  {b['category']}: budget {_currency(b['monthly_limit'])}, spent {_currency(actual)}")

    merchant_list = [
        {"merchant": m, "total": round(info["total"], 2), "count": info["count"]}
        for m, info in top_merchants
    ]
    categories_json = json.dumps(categories[:10], indent=2)
    merchants_json = json.dumps(merchant_list, indent=2)
    budgets_text = chr(10).join(budget_status) if budget_status else "No budgets set."

    prompt = f"""You are a personal finance analyst. Analyze this financial data for {period_label} and generate exactly 20 concise, actionable insights as a JSON array of strings.

INCOME & EXPENSES:
- Income: {_currency(income_expenses['income'])}
- Expenses: {_currency(income_expenses['expenses'])}
- Net Savings: {_currency(income_expenses['net'])}
- Daily Average Spending: {_currency(daily_avg)}

PREVIOUS PERIOD COMPARISON:
- Previous Income: {_currency(prev_ie['income'])}
- Previous Expenses: {_currency(prev_ie['expenses'])}
- Previous Net: {_currency(prev_ie['net'])}
- Income Change: {_change_str(income_expenses['income'], prev_ie['income'])}
- Expense Change: {_change_str(income_expenses['expenses'], prev_ie['expenses'])}

SPENDING BY CATEGORY (top 10):
{categories_json}

TOP MERCHANTS:
{merchants_json}

RECURRING/SUBSCRIPTIONS:
- Total Monthly: {_currency(recurring_data.get('total_monthly_cost', 0))}
- Count: {len(recurring_data.get('items', []))} recurring charges

BUDGETS:
{budgets_text}

Generate 20 insights covering:
1. Overall financial health assessment (savings rate, income vs expenses trend)
2. Spending patterns — where money is going, any concerning trends
3. Category-specific observations — which categories are high/low, comparisons to typical US spending
4. Month-over-month changes — what improved, what got worse
5. Merchant-level insights — concentrated spending, potential savings
6. Budget adherence — which budgets are on track, which are over
7. Subscription/recurring cost observations
8. Actionable recommendations — specific things to do to save money
9. Positive reinforcement — what's going well
10. Forward-looking advice — what to watch for next month

Use specific dollar amounts. Keep each insight to 1-2 sentences. Be direct, specific, and helpful.
Return ONLY a JSON array of 20 strings."""

    try:
        response_text = await ai_service._call_gemini(prompt, temperature=0.3, json_mode=True)
        insights = json.loads(response_text)
        if isinstance(insights, dict):
            insights = insights.get("insights", [])
        if isinstance(insights, list):
            return [str(i) for i in insights[:20]]
    except Exception:
        pass
    return []


def _add_ai_insights(story, styles, insights: list[str]):
    if not insights:
        return
    story.append(Paragraph("AI Financial Insights", styles["SectionHeader"]))
    items = [
        ListItem(Paragraph(insight, styles["BulletText"]))
        for insight in insights
    ]
    story.append(ListFlowable(items, bulletType="bullet", bulletFontSize=6, bulletOffsetY=-2, start="circle"))


# ── Report generators ────────────────────────────────────────────────────────


class ReportService:

    async def generate_monthly_report(
        self, user_id: uuid.UUID, year: int, month: int,
        db: AsyncSession, user_email: str = "",
    ) -> bytes:
        start = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        end = date(year, month, last_day)
        month_name = calendar.month_name[month]

        # Current period data
        income_expenses = await analytics.get_income_vs_expenses(user_id, start, end, db)
        categories = await analytics.get_spending_by_category(user_id, start, end, db)
        transactions = await analytics.get_transactions_for_period(user_id, start, end, db)
        budgets = await _get_budgets(user_id, db)
        recurring_data = await recurring_svc.detect_recurring(user_id=user_id, db=db)

        # Previous month
        if month == 1:
            prev_start, prev_end = date(year - 1, 12, 1), date(year - 1, 12, 31)
            prev_label = f"Dec {year - 1}"
        else:
            prev_start = date(year, month - 1, 1)
            prev_end = date(year, month - 1, calendar.monthrange(year, month - 1)[1])
            prev_label = f"{calendar.month_abbr[month - 1]} {year}"
        prev_ie = await analytics.get_income_vs_expenses(user_id, prev_start, prev_end, db)

        # Derived
        top_merch = _top_merchants(transactions)
        income = income_expenses["income"]
        expenses = income_expenses["expenses"]
        net = income_expenses["net"]
        savings_rate = (net / income * 100) if income > 0 else 0
        daily_avg = round(expenses / last_day, 2) if last_day > 0 else 0

        # AI insights (Gemini — free)
        ai_insights = await _generate_ai_insights(
            f"{month_name} {year}", income_expenses, categories,
            top_merch, prev_ie, recurring_data, budgets, daily_avg,
        )

        # Build PDF
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                                topMargin=0.75 * inch, bottomMargin=0.75 * inch)
        styles = _build_styles()
        story = []

        # Header
        story.append(Paragraph("Monthly Financial Report", styles["ReportTitle"]))
        story.append(Paragraph(f"{month_name} {year} &bull; {user_email}", styles["ReportSubtitle"]))

        # 1. Summary
        story.append(Paragraph("Income & Expenses Summary", styles["SectionHeader"]))
        story.append(_summary_table([
            ["Total Income", "Total Expenses", "Net Savings", "Savings Rate"],
            [_currency(income), _currency(expenses), _currency(net), _pct(savings_rate)],
        ]))

        # 2. Month-over-month comparison
        _add_comparison(story, styles, income_expenses, prev_ie,
                        f"{calendar.month_abbr[month]} {year}", prev_label)

        # 3. Daily spending
        _add_daily_avg(story, styles, expenses, last_day, transactions)

        # 4. Categories
        if categories:
            story.append(Paragraph("Spending by Category", styles["SectionHeader"]))
            total_spending = sum(c["total"] for c in categories)
            cat_rows = [[c["category"], _currency(c["total"]),
                         _pct(c["total"] / total_spending * 100 if total_spending else 0),
                         str(c["count"])] for c in categories]
            story.append(_make_table(
                ["Category", "Amount", "% of Total", "Transactions"],
                cat_rows, col_widths=[2.5 * inch, 1.5 * inch, 1 * inch, 1 * inch],
            ))

        # 5. Top merchants
        if top_merch:
            story.append(Paragraph("Top 10 Merchants", styles["SectionHeader"]))
            rows = [[n, _currency(i["total"]), str(i["count"])] for n, i in top_merch]
            story.append(_make_table(
                ["Merchant", "Total Spent", "Transactions"],
                rows, col_widths=[3 * inch, 1.5 * inch, 1.5 * inch],
            ))

        # 6. Largest single expenses
        _add_largest_expenses(story, styles, transactions)

        # 7. Income sources
        _add_income_sources(story, styles, transactions)

        # 8. Recurring & subscriptions
        _add_recurring(story, styles, recurring_data)

        # 9. Budget performance
        if budgets:
            cat_spending = {c["category"]: c["total"] for c in categories}
            story.append(Paragraph("Budget Performance", styles["SectionHeader"]))
            budget_rows = []
            for b in budgets:
                actual = cat_spending.get(b["category"], 0)
                remaining = b["monthly_limit"] - actual
                pct_used = (actual / b["monthly_limit"] * 100) if b["monthly_limit"] > 0 else 0
                status = "Over" if remaining < 0 else "Under"
                budget_rows.append([
                    b["category"], _currency(b["monthly_limit"]), _currency(actual),
                    _currency(abs(remaining)), f"{_pct(pct_used)} ({status})",
                ])
            story.append(_make_table(
                ["Category", "Budget", "Actual", "Remaining", "% Used"],
                budget_rows, col_widths=[1.8 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch],
            ))

        # 10. AI Insights
        _add_ai_insights(story, styles, ai_insights)

        doc.build(story)
        return buf.getvalue()

    async def generate_annual_report(
        self, user_id: uuid.UUID, year: int,
        db: AsyncSession, user_email: str = "",
    ) -> bytes:
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        num_days = 366 if calendar.isleap(year) else 365

        # Full-year data
        income_expenses = await analytics.get_income_vs_expenses(user_id, start, end, db)
        categories = await analytics.get_spending_by_category(user_id, start, end, db)
        transactions = await analytics.get_transactions_for_period(user_id, start, end, db)
        budgets = await _get_budgets(user_id, db)
        recurring_data = await recurring_svc.detect_recurring(user_id=user_id, db=db)

        # Previous year
        prev_start, prev_end = date(year - 1, 1, 1), date(year - 1, 12, 31)
        prev_ie = await analytics.get_income_vs_expenses(user_id, prev_start, prev_end, db)

        # Monthly trend
        monthly_data = []
        for m in range(1, 13):
            m_start = date(year, m, 1)
            m_end = date(year, m, calendar.monthrange(year, m)[1])
            ie = await analytics.get_income_vs_expenses(user_id, m_start, m_end, db)
            monthly_data.append({"month": calendar.month_abbr[m], **ie})

        # Derived
        top_merch = _top_merchants(transactions)
        income = income_expenses["income"]
        expenses = income_expenses["expenses"]
        net = income_expenses["net"]
        savings_rate = (net / income * 100) if income > 0 else 0
        daily_avg = round(expenses / num_days, 2) if num_days > 0 else 0

        # AI insights
        ai_insights = await _generate_ai_insights(
            str(year), income_expenses, categories,
            top_merch, prev_ie, recurring_data, budgets, daily_avg,
        )

        # Build PDF
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                                topMargin=0.75 * inch, bottomMargin=0.75 * inch)
        styles = _build_styles()
        story = []

        # Header
        story.append(Paragraph("Annual Financial Report", styles["ReportTitle"]))
        story.append(Paragraph(f"{year} &bull; {user_email}", styles["ReportSubtitle"]))

        # 1. Summary
        story.append(Paragraph("Income & Expenses Summary", styles["SectionHeader"]))
        story.append(_summary_table([
            ["Total Income", "Total Expenses", "Net Savings", "Savings Rate"],
            [_currency(income), _currency(expenses), _currency(net), _pct(savings_rate)],
        ]))

        # 2. Year-over-year comparison
        _add_comparison(story, styles, income_expenses, prev_ie, str(year), str(year - 1))

        # 3. Daily spending
        _add_daily_avg(story, styles, expenses, num_days, transactions)

        # 4. Monthly trend
        story.append(Paragraph("Monthly Trend", styles["SectionHeader"]))
        trend_rows = [[md["month"], _currency(md["income"]), _currency(md["expenses"]),
                        _currency(md["net"])] for md in monthly_data]
        trend_rows.append(["TOTAL", _currency(income), _currency(expenses), _currency(net)])
        trend_table = _make_table(
            ["Month", "Income", "Expenses", "Net"],
            trend_rows, col_widths=[1.5 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch],
        )
        last_row = len(trend_rows)
        ts = trend_table.getStyle()
        ts.add("FONTNAME", (0, last_row), (-1, last_row), "Helvetica-Bold")
        ts.add("BACKGROUND", (0, last_row), (-1, last_row), EMERALD_LIGHT)
        story.append(trend_table)

        # 5. Categories
        if categories:
            story.append(Paragraph("Spending by Category", styles["SectionHeader"]))
            total_spending = sum(c["total"] for c in categories)
            cat_rows = [[c["category"], _currency(c["total"]),
                         _pct(c["total"] / total_spending * 100 if total_spending else 0),
                         str(c["count"])] for c in categories]
            story.append(_make_table(
                ["Category", "Amount", "% of Total", "Transactions"],
                cat_rows, col_widths=[2.5 * inch, 1.5 * inch, 1 * inch, 1 * inch],
            ))

        # 6. Top merchants
        if top_merch:
            story.append(Paragraph("Top 10 Merchants", styles["SectionHeader"]))
            rows = [[n, _currency(i["total"]), str(i["count"])] for n, i in top_merch]
            story.append(_make_table(
                ["Merchant", "Total Spent", "Transactions"],
                rows, col_widths=[3 * inch, 1.5 * inch, 1.5 * inch],
            ))

        # 7. Largest single expenses
        _add_largest_expenses(story, styles, transactions)

        # 8. Income sources
        _add_income_sources(story, styles, transactions)

        # 9. Recurring & subscriptions
        _add_recurring(story, styles, recurring_data)

        # 10. Budget performance (annualized)
        if budgets:
            cat_spending = {c["category"]: c["total"] for c in categories}
            story.append(Paragraph("Budget Performance (Annualized)", styles["SectionHeader"]))
            budget_rows = []
            for b in budgets:
                annual_limit = b["monthly_limit"] * 12
                actual = cat_spending.get(b["category"], 0)
                remaining = annual_limit - actual
                pct_used = (actual / annual_limit * 100) if annual_limit > 0 else 0
                status = "Over" if remaining < 0 else "Under"
                budget_rows.append([
                    b["category"], _currency(annual_limit), _currency(actual),
                    _currency(abs(remaining)), f"{_pct(pct_used)} ({status})",
                ])
            story.append(_make_table(
                ["Category", "Annual Budget", "Actual", "Remaining", "% Used"],
                budget_rows, col_widths=[1.8 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch],
            ))

        # 11. AI Insights
        _add_ai_insights(story, styles, ai_insights)

        doc.build(story)
        return buf.getvalue()
