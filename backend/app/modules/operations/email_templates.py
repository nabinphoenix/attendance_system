"""Branded multipart email templates used by the notification worker."""

from html import escape

from app.core.config import settings


def public_url(path: str = "") -> str:
    return f"{settings.frontend_url.rstrip('/')}{path}"


def _html(value: object) -> str:
    return escape(str(value), quote=True)


def branded_email(
    *,
    title: str,
    greeting_name: str,
    intro: str,
    details: list[tuple[str, str]] | None = None,
    action_label: str | None = None,
    action_url: str | None = None,
    closing: str = "If you need help, please contact your college administrator.",
) -> str:
    """Return broadly compatible HTML with inline styles for email clients."""

    rows = "".join(
        f'<tr><td style="padding:10px 0;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:14px">{_html(label)}</td>'
        f'<td style="padding:10px 0;border-bottom:1px solid #e2e8f0;color:#0f172a;font-size:14px;font-weight:700;text-align:right">{_html(value)}</td></tr>'
        for label, value in (details or [])
    )
    details_html = (
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:22px 0;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:0 16px">{rows}</table>'
        if rows
        else ""
    )
    action_html = (
        f'<table role="presentation" cellspacing="0" cellpadding="0" style="margin:26px 0"><tr><td style="border-radius:8px;background:#059669">'
        f'<a href="{_html(action_url)}" style="display:inline-block;padding:13px 22px;color:#ffffff;font-size:15px;font-weight:700;text-decoration:none">{_html(action_label)}</a>'
        f'</td></tr></table><p style="margin:0;color:#64748b;font-size:12px;line-height:18px;word-break:break-all">If the button does not open, copy this link into your browser:<br /><a href="{_html(action_url)}" style="color:#047857">{_html(action_url)}</a></p>'
        if action_label and action_url
        else ""
    )
    logo_url = _html(public_url("/antimbench-logo.svg"))
    return f"""<!doctype html>
<html lang="en">
  <head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" /></head>
  <body style="margin:0;padding:0;background:#eef5f3;font-family:Arial,Helvetica,sans-serif;color:#0f172a">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0">{_html(title)}</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#eef5f3;padding:28px 12px"><tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;background:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 8px 24px rgba(15,23,42,.08)">
        <tr><td style="padding:24px 30px;background:#063d36;color:#ffffff">
          <table role="presentation" cellspacing="0" cellpadding="0"><tr>
            <td style="padding-right:13px"><img src="{logo_url}" width="46" height="34" alt="AntimBench" style="display:block;border:0;outline:none" /></td>
            <td><div style="font-size:21px;font-weight:700;line-height:24px">AntimBench</div><div style="font-size:12px;color:#b7e4d7;line-height:18px">Attendance &amp; Student Support</div></td>
          </tr></table>
        </td></tr>
        <tr><td style="padding:32px 30px 28px">
          <h1 style="margin:0 0 20px;color:#0f172a;font-size:25px;line-height:32px">{_html(title)}</h1>
          <p style="margin:0 0 14px;color:#334155;font-size:16px;line-height:25px">Hello <strong>{_html(greeting_name)}</strong>,</p>
          <p style="margin:0;color:#334155;font-size:16px;line-height:25px">{_html(intro)}</p>
          {details_html}
          {action_html}
          <p style="margin:24px 0 0;color:#475569;font-size:14px;line-height:22px">{_html(closing)}</p>
        </td></tr>
        <tr><td style="padding:18px 30px;background:#f8fafc;border-top:1px solid #e2e8f0;color:#64748b;font-size:12px;line-height:18px">This is an automated message from AntimBench. Please do not share secure account links with anyone.</td></tr>
      </table>
    </td></tr></table>
  </body>
</html>"""


def invitation_email(*, student_name: str, email: str, setup_url: str, expires_hours: int, welcome: bool, has_account: bool) -> tuple[str, str, str]:
    if welcome:
        subject = "Your AntimBench student account is ready"
        title = "Your student account is ready"
        intro = "Your AntimBench account has been created. Use the secure link below to choose your own password before signing in."
    elif has_account:
        subject = "Set your AntimBench password"
        title = "Set your password"
        intro = "A password-setup link was requested for your existing AntimBench account. Choose a new password using the secure link below."
    else:
        subject = "Activate your AntimBench account"
        title = "Activate your account"
        intro = "Your AntimBench profile is ready. Use the secure link below to activate your account and choose a password."
    plain = (
        f"Hello {student_name},\n\n{intro}\n\n"
        f"Sign-in email: {email}\n\n"
        "For your security, choose your own password. AntimBench will never send a password by email.\n"
        f"This secure link expires in {expires_hours} hours.\n\n"
        f"Complete account setup: {setup_url}"
    )
    html = branded_email(
        title=title,
        greeting_name=student_name,
        intro=intro,
        details=[("Sign-in email", email), ("Link expiry", f"{expires_hours} hours")],
        action_label="Complete account setup" if welcome or not has_account else "Set my password",
        action_url=setup_url,
        closing="For your security, choose your own password. AntimBench will never send a password by email.",
    )
    return subject, plain, html


def attendance_alert_email(*, student_name: str, module_name: str, module_code: str | None, class_types: list[str], percentage: float, threshold: float, total_classes: int) -> tuple[str, str, str]:
    module = f"{module_name} ({module_code})" if module_code else module_name
    class_type_text = ", ".join(class_types) or "Scheduled class"
    subject = "Attendance alert: action needed"
    plain = (
        f"Hello {student_name},\n\n"
        f"Your attendance in {module} has dropped below {threshold:g}%.\n"
        f"Current attendance: {percentage:.2f}%\n"
        f"Module name: {module_name}\n"
        f"Module code: {module_code or 'Not assigned'}\n"
        f"Class type: {class_type_text}\n\n"
        "Please attend upcoming classes and contact your teacher or college administrator if you need support."
    )
    html = branded_email(
        title="Your attendance needs attention",
        greeting_name=student_name,
        intro=f"Your attendance has fallen below the {threshold:g}% support threshold. Please review this module and attend upcoming classes.",
        details=[
            ("Module", module_name),
            ("Module code", module_code or "Not assigned"),
            ("Current attendance", f"{percentage:.2f}%"),
            ("Required threshold", f"{threshold:g}%"),
            ("Completed classes", str(total_classes)),
            ("Class type", class_type_text),
        ],
        action_label="View my attendance",
        action_url=public_url("/student/reports"),
        closing="Please attend upcoming classes and contact your teacher or college administrator if you need support.",
    )
    return subject, plain, html


def plain_text_email_html(subject: str, body: str) -> str:
    return branded_email(
        title=subject,
        greeting_name="there",
        intro=" ".join(body.splitlines()),
        closing="Please contact your college administrator if you need support.",
    )
