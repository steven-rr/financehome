import logging
from datetime import date, timedelta

import resend
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.budget import Budget
from app.models.notification_preference import NotificationPreference
from app.models.user import User
from app.services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self):
        resend.api_key = settings.resend_api_key

    async def send_email(self, to: str, subject: str, html: str) -> bool:
        if not settings.resend_api_key:
            logger.warning("Resend API key not configured — skipping email to %s", to)
            return False
        try:
            resend.Emails.send(
                {
                    "from": settings.alert_from_email,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                }
            )
            return True
        except Exception:
            logger.exception("Failed to send email to %s", to)
            return False

    # ── Digest ───────────────────────────────────────────────────

    async def send_digest(self, user: User, db: AsyncSession) -> bool:
        analytics = AnalyticsService()
        end = date.today()
        start = end - timedelta(days=7)
        month_start = end.replace(day=1)

        income_expenses = await analytics.get_income_vs_expenses(user.id, start, end, db)
        categories = await analytics.get_spending_by_category(user.id, start, end, db)
        transactions = await analytics.get_transactions_for_period(user.id, start, end, db)

        # Sort transactions by amount descending for largest purchases
        top_transactions = sorted(transactions, key=lambda t: t["amount"], reverse=True)[:5]

        # Budget status (month-to-date)
        budget_result = await db.execute(select(Budget).where(Budget.user_id == user.id))
        budgets = budget_result.scalars().all()
        budget_status = []
        if budgets:
            month_cats = await analytics.get_spending_by_category(user.id, month_start, end, db)
            cat_map = {c["category"]: c["total"] for c in month_cats}
            for b in budgets:
                actual = cat_map.get(b.category, 0.0)
                pct = (actual / b.monthly_limit * 100) if b.monthly_limit else 0
                if pct >= 80:
                    budget_status.append(
                        {"category": b.category, "limit": b.monthly_limit, "actual": actual, "pct": round(pct)}
                    )

        html = self._render_digest(
            user_email=user.email,
            start=start,
            end=end,
            income=income_expenses["income"],
            expenses=income_expenses["expenses"],
            net=income_expenses["net"],
            categories=categories[:5],
            top_transactions=top_transactions,
            budget_status=budget_status,
        )

        subject = f"Your Weekly Financial Digest — {start.strftime('%b %d')} to {end.strftime('%b %d, %Y')}"
        return await self.send_email(user.email, subject, html)

    def _render_digest(
        self,
        user_email: str,
        start: date,
        end: date,
        income: float,
        expenses: float,
        net: float,
        categories: list[dict],
        top_transactions: list[dict],
        budget_status: list[dict],
    ) -> str:
        # Category rows
        cat_rows = ""
        for c in categories:
            cat_rows += f"""
            <tr>
              <td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;">{c['category']}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:right;">${c['total']:,.2f}</td>
            </tr>"""

        # Top transactions rows
        txn_rows = ""
        for t in top_transactions:
            merchant = t.get("merchant_name") or t.get("description", "Unknown")
            if len(merchant) > 35:
                merchant = merchant[:32] + "..."
            txn_rows += f"""
            <tr>
              <td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;">{merchant}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:right;">${t['amount']:,.2f}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:right;">{t.get('date', '')}</td>
            </tr>"""

        # Budget warnings
        budget_html = ""
        if budget_status:
            budget_rows = ""
            for b in budget_status:
                color = "#dc2626" if b["pct"] >= 100 else "#d97706"
                budget_rows += f"""
                <tr>
                  <td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;">{b['category']}</td>
                  <td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:right;">${b['actual']:,.2f} / ${b['limit']:,.2f}</td>
                  <td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:right;color:{color};font-weight:600;">{b['pct']}%</td>
                </tr>"""
            budget_html = f"""
            <h2 style="color:#059669;font-size:18px;margin:28px 0 12px;">Budget Alerts</h2>
            <table style="width:100%;border-collapse:collapse;font-size:14px;">
              <tr style="background:#f1f5f9;">
                <th style="padding:8px 12px;text-align:left;">Category</th>
                <th style="padding:8px 12px;text-align:right;">Spent / Limit</th>
                <th style="padding:8px 12px;text-align:right;">Used</th>
              </tr>
              {budget_rows}
            </table>"""

        net_color = "#059669" if net >= 0 else "#dc2626"

        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:8px;overflow:hidden;margin-top:20px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
    <!-- Header -->
    <div style="background:#059669;padding:24px 32px;">
      <h1 style="color:#ffffff;margin:0;font-size:22px;">FinanceHome Weekly Digest</h1>
      <p style="color:#d1fae5;margin:4px 0 0;font-size:14px;">{start.strftime('%b %d')} — {end.strftime('%b %d, %Y')}</p>
    </div>

    <div style="padding:24px 32px;">
      <!-- Summary -->
      <h2 style="color:#059669;font-size:18px;margin:0 0 12px;">Weekly Summary</h2>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr>
          <td style="padding:10px 12px;background:#f0fdf4;border-radius:6px 0 0 6px;"><strong>Income</strong></td>
          <td style="padding:10px 12px;background:#f0fdf4;text-align:right;color:#059669;font-weight:600;border-radius:0 6px 6px 0;">${income:,.2f}</td>
        </tr>
        <tr><td colspan="2" style="height:4px;"></td></tr>
        <tr>
          <td style="padding:10px 12px;background:#fef2f2;border-radius:6px 0 0 6px;"><strong>Expenses</strong></td>
          <td style="padding:10px 12px;background:#fef2f2;text-align:right;color:#dc2626;font-weight:600;border-radius:0 6px 6px 0;">${expenses:,.2f}</td>
        </tr>
        <tr><td colspan="2" style="height:4px;"></td></tr>
        <tr>
          <td style="padding:10px 12px;background:#f8fafc;border-radius:6px 0 0 6px;"><strong>Net</strong></td>
          <td style="padding:10px 12px;background:#f8fafc;text-align:right;color:{net_color};font-weight:600;border-radius:0 6px 6px 0;">${net:,.2f}</td>
        </tr>
      </table>

      <!-- Top Categories -->
      <h2 style="color:#059669;font-size:18px;margin:28px 0 12px;">Top Spending Categories</h2>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr style="background:#f1f5f9;">
          <th style="padding:8px 12px;text-align:left;">Category</th>
          <th style="padding:8px 12px;text-align:right;">Amount</th>
        </tr>
        {cat_rows}
      </table>

      <!-- Largest Transactions -->
      <h2 style="color:#059669;font-size:18px;margin:28px 0 12px;">Largest Transactions</h2>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr style="background:#f1f5f9;">
          <th style="padding:8px 12px;text-align:left;">Merchant</th>
          <th style="padding:8px 12px;text-align:right;">Amount</th>
          <th style="padding:8px 12px;text-align:right;">Date</th>
        </tr>
        {txn_rows}
      </table>

      {budget_html}

      <!-- CTA -->
      <div style="text-align:center;margin-top:32px;">
        <a href="{settings.frontend_url}" style="display:inline-block;background:#059669;color:#ffffff;text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:600;font-size:14px;">Open FinanceHome</a>
      </div>

      <p style="color:#94a3b8;font-size:12px;margin-top:24px;text-align:center;">
        You're receiving this because you have email digests enabled.
        Manage your preferences in Settings.
      </p>
    </div>
  </div>
</body>
</html>"""

    # ── Alert Emails ─────────────────────────────────────────────

    async def send_budget_alert(self, to: str, category: str, limit: float, actual: float) -> bool:
        pct = round(actual / limit * 100) if limit else 0
        html = self._render_alert(
            title=f"Budget Exceeded: {category}",
            body=f"Your <strong>{category}</strong> budget of <strong>${limit:,.2f}</strong> has been exceeded. "
            f"You've spent <strong>${actual:,.2f}</strong> this month ({pct}% of budget).",
            color="#dc2626",
        )
        return await self.send_email(to, f"Budget Alert: {category} at {pct}%", html)

    async def send_large_transaction_alert(
        self, to: str, amount: float, merchant: str, txn_date: str
    ) -> bool:
        html = self._render_alert(
            title="Large Transaction Detected",
            body=f"A transaction of <strong>${amount:,.2f}</strong> was recorded at "
            f"<strong>{merchant}</strong> on {txn_date}.",
            color="#d97706",
        )
        return await self.send_email(to, f"Large Transaction: ${amount:,.2f} at {merchant}", html)

    def _render_alert(self, title: str, body: str, color: str) -> str:
        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:8px;overflow:hidden;margin-top:20px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
    <div style="background:{color};padding:20px 32px;">
      <h1 style="color:#ffffff;margin:0;font-size:20px;">{title}</h1>
    </div>
    <div style="padding:24px 32px;">
      <p style="font-size:15px;line-height:1.6;color:#334155;">{body}</p>
      <div style="text-align:center;margin-top:24px;">
        <a href="{settings.frontend_url}" style="display:inline-block;background:#059669;color:#ffffff;text-decoration:none;padding:10px 20px;border-radius:6px;font-weight:600;font-size:14px;">View in FinanceHome</a>
      </div>
      <p style="color:#94a3b8;font-size:12px;margin-top:20px;text-align:center;">
        Manage alert preferences in Settings.
      </p>
    </div>
  </div>
</body>
</html>"""
