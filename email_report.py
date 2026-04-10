"""
HTML email report generator and sender for the Greyhound prediction pipeline.

Generates a mobile-friendly HTML email from the scored DataFrame and sends it
via SMTP (smtplib).  Falls back to saving the HTML to disk if sending fails.

Public API:
    generate_html_report(df, top4, date_str) -> str
    send_email(html, subject, config)        -> bool
    save_html_fallback(html, date_str)       -> str
"""

import os
import smtplib
import textwrap
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import pandas as pd

AEST = timezone(timedelta(hours=10))  # Australia/Brisbane — no DST

# Rank colours
_COLOURS = {1: "#22c55e", 2: "#f59e0b", 3: "#6b7280", 4: "#6b7280"}
_RANK_LABELS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}


# ──────────────────────────────────────────────────────────────────────────────
# HTML generation
# ──────────────────────────────────────────────────────────────────────────────

def _format_time(raw: Any) -> str:
    """Parse ISO datetime or time string and return HH:MM AM/PM."""
    if pd.isna(raw) or not raw:
        return str(raw)
    try:
        dt = datetime.fromisoformat(str(raw))
        return dt.strftime("%I:%M %p")
    except (ValueError, TypeError):
        return str(raw)


def _score_bar(score: float, colour: str) -> str:
    """Return an inline-CSS score bar HTML snippet."""
    pct = max(0, min(100, round(score * 100, 1)))
    return (
        f'<div style="background:#334155;border-radius:4px;height:8px;'
        f'width:120px;display:inline-block;vertical-align:middle;">'
        f'<div style="background:{colour};height:8px;border-radius:4px;'
        f'width:{pct}%;"></div></div>'
    )


def _build_race_card(race_df: pd.DataFrame, race_info: pd.Series) -> str:
    """Render a single race card as an HTML table."""
    try:
        time_str = _format_time(race_info.get("race_time", ""))
    except Exception:
        time_str = str(race_info.get("race_time", ""))

    distance = race_info.get("distance", "")
    grade = race_info.get("grade", "")
    race_name = race_info.get("race_name", "")
    race_num = race_info.get("race_number", "")

    header = (
        f'<div style="background:#1e293b;border-radius:8px;padding:12px 16px;'
        f'margin-bottom:12px;">'
        f'<div style="color:#94a3b8;font-size:12px;margin-bottom:4px;">'
        f'Race {race_num} &bull; {time_str} &bull; {distance} &bull; {grade}'
        f'</div>'
        f'<div style="color:#f1f5f9;font-size:14px;font-weight:600;">{race_name}</div>'
    )

    rows = ""
    for _, runner in race_df.sort_values("predicted_rank").iterrows():
        rank = int(runner.get("predicted_rank", 1))
        colour = _COLOURS.get(rank, "#6b7280")
        composite = runner.get("composite", 0.0)
        win_prob = runner.get("win_prob", 0.0)
        implied_odds = runner.get("implied_odds", 0.0)
        dog_name = str(runner.get("dog_name", ""))
        box_num = runner.get("box", "")

        win_pct = f"{win_prob:.0%}" if pd.notna(win_prob) else "—"
        odds_str = f"${implied_odds:.1f}" if pd.notna(implied_odds) else "—"

        rows += (
            f'<tr style="border-top:1px solid #334155;">'
            f'<td style="padding:8px 4px;width:28px;">'
            f'<span style="background:{colour};color:#fff;border-radius:50%;'
            f'display:inline-block;width:20px;height:20px;text-align:center;'
            f'line-height:20px;font-size:11px;font-weight:700;">{rank}</span>'
            f'</td>'
            f'<td style="padding:8px 4px;width:30px;color:#94a3b8;font-size:13px;">'
            f'B{box_num}</td>'
            f'<td style="padding:8px 8px;color:#f1f5f9;font-size:14px;'
            f'font-weight:600;min-width:140px;">{dog_name[:22]}</td>'
            f'<td style="padding:8px 4px;">{_score_bar(float(composite) if pd.notna(composite) else 0.0, colour)}</td>'
            f'<td style="padding:8px 8px;color:{colour};font-size:13px;'
            f'font-weight:700;text-align:right;">{win_pct}</td>'
            f'<td style="padding:8px 4px;color:#94a3b8;font-size:12px;'
            f'text-align:right;">{odds_str}</td>'
            f'</tr>'
        )

    table = (
        f'<table style="width:100%;border-collapse:collapse;font-family:sans-serif;">'
        f'<thead><tr style="background:#0f172a;">'
        f'<th style="padding:6px 4px;color:#64748b;font-size:11px;text-align:left;" colspan="2">Rank</th>'
        f'<th style="padding:6px 4px;color:#64748b;font-size:11px;text-align:left;">Dog</th>'
        f'<th style="padding:6px 4px;color:#64748b;font-size:11px;">Score</th>'
        f'<th style="padding:6px 4px;color:#64748b;font-size:11px;text-align:right;">Win%</th>'
        f'<th style="padding:6px 4px;color:#64748b;font-size:11px;text-align:right;">Odds</th>'
        f'</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table>'
    )

    return header + table + "</div>"


def generate_html_report(
    df: pd.DataFrame,
    top4: pd.DataFrame,
    date_str: str,
) -> str:
    """
    Generate a mobile-friendly HTML email report from scored DataFrames.

    Parameters
    ----------
    df : pd.DataFrame
        Full scored DataFrame (output of scorer.predict).
    top4 : pd.DataFrame
        Top-4 picks per race (output of scorer.get_top4).
    date_str : str
        Date string in YYYY-MM-DD format.

    Returns
    -------
    str
        Complete HTML document as a string.
    """
    now = datetime.now(AEST)
    timestamp = now.strftime("%d %b %Y %I:%M %p AEST")

    # Summary stats
    if df.empty or top4.empty:
        n_venues = n_races = n_strong = 0
    else:
        n_venues = int(df["venue"].nunique()) if "venue" in df.columns else 0
        n_races = int(df.groupby(["venue", "race_number"]).ngroups) if "venue" in df.columns else 0
        threshold = 0.25
        n_strong = int(
            (top4[top4["predicted_rank"] == 1]["win_prob"] > threshold).sum()
        ) if "win_prob" in top4.columns else 0

    summary_html = (
        f'<div style="background:#1e293b;border-radius:12px;padding:20px;'
        f'margin-bottom:24px;text-align:center;">'
        f'<div style="color:#94a3b8;font-size:13px;margin-bottom:8px;">{date_str}</div>'
        f'<div style="display:flex;justify-content:space-around;flex-wrap:wrap;gap:16px;">'
        f'<div><div style="color:#22c55e;font-size:28px;font-weight:700;">{n_venues}</div>'
        f'<div style="color:#94a3b8;font-size:12px;">Venues</div></div>'
        f'<div><div style="color:#22c55e;font-size:28px;font-weight:700;">{n_races}</div>'
        f'<div style="color:#94a3b8;font-size:12px;">Races</div></div>'
        f'<div><div style="color:#f59e0b;font-size:28px;font-weight:700;">{n_strong}</div>'
        f'<div style="color:#94a3b8;font-size:12px;">Strong Picks (&gt;25%)</div></div>'
        f'</div></div>'
    )

    # Per-venue sections
    venues_html = ""
    if not top4.empty and "venue" in top4.columns:
        race_info_cols = ["venue", "state", "race_number", "race_name",
                          "race_time", "distance", "grade"]
        existing_info_cols = [c for c in race_info_cols if c in df.columns]

        for venue in sorted(top4["venue"].unique()):
            state = ""
            if "state" in df.columns:
                state_vals = df[df["venue"] == venue]["state"].dropna()
                state = f" ({state_vals.iloc[0]})" if not state_vals.empty else ""

            venues_html += (
                f'<div style="margin-bottom:24px;">'
                f'<div style="background:#0f172a;color:#22c55e;font-size:16px;'
                f'font-weight:700;padding:12px 16px;border-radius:8px 8px 0 0;'
                f'border-left:4px solid #22c55e;">{venue}{state}</div>'
            )

            venue_top4 = top4[top4["venue"] == venue]
            for race_num in sorted(venue_top4["race_number"].unique()):
                race_df = venue_top4[venue_top4["race_number"] == race_num]

                # Build race_info from df
                if existing_info_cols and not df.empty:
                    race_rows = df[
                        (df["venue"] == venue) & (df["race_number"] == race_num)
                    ]
                    race_info = race_rows[existing_info_cols].iloc[0] if not race_rows.empty else pd.Series()
                else:
                    race_info = pd.Series({"race_number": race_num})

                venues_html += _build_race_card(race_df, race_info)

            venues_html += "</div>"

    # Footer
    footer_html = (
        f'<div style="text-align:center;color:#475569;font-size:11px;'
        f'padding:20px;border-top:1px solid #1e293b;margin-top:24px;">'
        f'Generated {timestamp}<br>'
        f'<em>For informational purposes only. Greyhound racing involves risk. '
        f'Bet responsibly. This is not financial advice.</em>'
        f'</div>'
    )

    html = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>Greyhound Picks — {date_str}</title>
        </head>
        <body style="margin:0;padding:0;background:#0f172a;font-family:-apple-system,
          BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
          <div style="max-width:600px;margin:0 auto;padding:16px;">
            <!-- Header -->
            <div style="text-align:center;padding:24px 0 16px;">
              <h1 style="color:#f1f5f9;font-size:22px;margin:0;">
                Greyhound Picks
              </h1>
            </div>
            <!-- Summary -->
            {summary_html}
            <!-- Venues -->
            {venues_html}
            <!-- Footer -->
            {footer_html}
          </div>
        </body>
        </html>
    """)

    return html


# ──────────────────────────────────────────────────────────────────────────────
# Email sending
# ──────────────────────────────────────────────────────────────────────────────

def send_email(html: str, subject: str, config: dict[str, Any]) -> bool:
    """
    Send an HTML email via SMTP (TLS).

    Credentials are read from config['smtp_user'] and config['smtp_pass'],
    which should have been populated from the SMTP_USER and SMTP_PASS
    environment variables by config_loader.get_smtp_config().

    Parameters
    ----------
    html : str
        HTML body of the email.
    subject : str
        Email subject line.
    config : dict
        SMTP configuration dict (from get_smtp_config()).

    Returns
    -------
    bool
        True if sent successfully, False otherwise.
    """
    smtp_host = config.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(config.get("smtp_port", 587))
    smtp_user = config.get("smtp_user", "")
    smtp_pass = config.get("smtp_pass", "")
    from_addr = config.get("from_address", "") or smtp_user
    to_addr = config.get("to_address", "")

    if not smtp_user or not smtp_pass:
        print("[email_report] ERROR: SMTP_USER and/or SMTP_PASS not set. Cannot send email.")
        return False
    if not to_addr:
        print("[email_report] ERROR: No recipient address (EMAIL_TO). Cannot send email.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        print(f"[email_report] Connecting to {smtp_host}:{smtp_port} ...")
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        print(f"[email_report] Email sent to {to_addr}")
        return True
    except smtplib.SMTPAuthenticationError:
        print(
            "[email_report] ERROR: SMTP authentication failed. "
            "For Gmail, use a 16-character App Password (not your account password)."
        )
    except smtplib.SMTPException as exc:
        print(f"[email_report] ERROR: SMTP error: {exc}")
    except OSError as exc:
        print(f"[email_report] ERROR: Network error: {exc}")
    return False


def save_html_fallback(html: str, date_str: str) -> str:
    """
    Save the HTML report to disk when email sending fails.

    Saves to outputs/report_{date}_{time}.html.

    Parameters
    ----------
    html : str
        HTML content to save.
    date_str : str
        Date string in YYYY-MM-DD format.

    Returns
    -------
    str
        Full path of the saved file.
    """
    now = datetime.now(AEST)
    time_part = now.strftime("%H%M")
    filename = f"report_{date_str}_{time_part}.html"
    outputs_dir = os.path.join(os.getcwd(), "outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    path = os.path.join(outputs_dir, filename)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"[email_report] HTML report saved to {path}")
    return path


# ──────────────────────────────────────────────────────────────────────────────
# Convenience wrapper
# ──────────────────────────────────────────────────────────────────────────────

def send_or_save(
    html: str,
    date_str: str,
    config: dict[str, Any],
    subject: str | None = None,
) -> str | None:
    """
    Attempt to send the HTML report via email; save to disk on failure.

    Parameters
    ----------
    html : str
        HTML report string.
    date_str : str
        Date string for subject line and fallback filename.
    config : dict
        Full pipeline config (uses config['email'] section).
    subject : str | None
        Optional subject override.

    Returns
    -------
    str | None
        Path to saved HTML file if email failed, else None.
    """
    subject = subject or f"Greyhound Picks — {date_str}"
    email_cfg = config.get("email", {})
    sent = send_email(html, subject, email_cfg)
    if not sent:
        return save_html_fallback(html, date_str)
    return None


if __name__ == "__main__":
    # Quick smoke test: generate an empty report and save it
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-10"
    report = generate_html_report(pd.DataFrame(), pd.DataFrame(), date)
    path = save_html_fallback(report, date)
    print(f"Smoke test OK — report at {path}")
