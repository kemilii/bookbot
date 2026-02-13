"""Email sending utilities for BookBot monthly recommendations."""

import logging
import os
import smtplib
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# SMTP configuration (from .env)
# ---------------------------------------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")


def _build_html(recs: list[dict], language: str, unsubscribe_url: str) -> str:
    """Render an HTML email body for the monthly recommendations."""
    is_zh = language == "zh"

    greeting = "Hi there!" if not is_zh else "你好！"
    intro = (
        "Here are your BookBot picks for this month:"
        if not is_zh
        else "这是 BookBot 为你精选的本月书单："
    )
    footer_text = (
        "You received this because you subscribed to BookBot monthly recommendations."
        if not is_zh
        else "你收到此邮件是因为你订阅了 BookBot 的每月推荐。"
    )
    unsub_text = "Unsubscribe" if not is_zh else "取消订阅"
    by_text = "by" if not is_zh else "作者："

    book_rows = ""
    for i, rec in enumerate(recs, 1):
        query = urllib.parse.quote(f"{rec['title']} {rec['author']}")
        if is_zh:
            search_url = f"https://search.douban.com/book/subject_search?search_text={query}"
            zlib_url = f"https://zh.zlib.li/s/{urllib.parse.quote(rec['title'])}"
        else:
            search_url = f"https://www.google.com/search?tbm=bks&q={query}"

        links_html = f'<a href="{search_url}" style="color:#4f6d7a;text-decoration:none;" target="_blank">{rec["title"]} &#8599;</a>'
        if is_zh:
            links_html += (
                f' &nbsp;|&nbsp; '
                f'<a href="{zlib_url}" style="color:#4f6d7a;text-decoration:none;font-size:13px;" target="_blank">Z-Library &#8599;</a>'
            )

        book_rows += f"""\
        <tr>
          <td style="padding:16px 20px;border-bottom:1px solid #e2e0dd;">
            <div style="font-size:13px;color:#6b6b6b;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">
              {"Pick" if not is_zh else "推荐"} {i}
            </div>
            <div style="font-size:17px;font-weight:600;color:#2c2c2c;margin-bottom:4px;">
              {links_html}
            </div>
            <div style="font-size:14px;color:#6b6b6b;margin-bottom:8px;">
              {by_text} {rec["author"]} &middot; {rec["publication_year"]}
            </div>
            <div style="font-size:15px;color:#2c2c2c;line-height:1.5;">
              {rec["explanation"]}
            </div>
          </td>
        </tr>
"""

    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#faf9f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#faf9f7;padding:40px 20px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
          <!-- Header -->
          <tr>
            <td style="padding:32px 24px 16px;text-align:center;">
              <div style="font-size:24px;font-weight:700;color:#2c2c2c;letter-spacing:-0.02em;">BookBot</div>
              <div style="font-size:15px;color:#6b6b6b;margin-top:4px;">
                {"Monthly Recommendations" if not is_zh else "每月推荐"}
              </div>
            </td>
          </tr>
          <!-- Greeting -->
          <tr>
            <td style="padding:8px 24px 16px;">
              <div style="font-size:16px;color:#2c2c2c;">{greeting}</div>
              <div style="font-size:15px;color:#6b6b6b;margin-top:4px;">{intro}</div>
            </td>
          </tr>
          <!-- Books -->
{book_rows}
          <!-- Footer -->
          <tr>
            <td style="padding:24px;text-align:center;">
              <div style="font-size:13px;color:#6b6b6b;margin-bottom:8px;">{footer_text}</div>
              <a href="{unsubscribe_url}" style="font-size:13px;color:#4f6d7a;">{unsub_text}</a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def send_recommendations_email(
    to_email: str,
    recs: list[dict],
    language: str,
    unsubscribe_token: str,
) -> bool:
    """Send a monthly recommendation email.

    Returns True on success, False on failure.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        logging.error("SMTP credentials not configured — skipping email to %s", to_email)
        return False

    unsubscribe_url = f"{BASE_URL}/api/unsubscribe/{unsubscribe_token}"
    subject = (
        "Your Monthly BookBot Recommendations"
        if language != "zh"
        else "BookBot 每月推荐书单"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = to_email
    msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"

    html_body = _build_html(recs, language, unsubscribe_url)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(EMAIL_FROM, [to_email], msg.as_string())
        logging.info("Email sent to %s", to_email)
        return True
    except Exception as exc:
        logging.error("Failed to send email to %s: %s", to_email, exc)
        return False
