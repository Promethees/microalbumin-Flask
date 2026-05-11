import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _smtp_connection():
    host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    port = int(os.environ.get('SMTP_PORT', '587'))
    user = os.environ.get('SMTP_USER', '')
    password = os.environ.get('SMTP_PASS', '')

    server = smtplib.SMTP(host, port, timeout=10)
    server.ehlo()
    server.starttls()
    server.login(user, password)
    return server, user


def send_verification_email(to_email: str, name: str, token: str, base_url: str):
    verify_url = f"{base_url.rstrip('/')}/api/account/verify/{token}"
    sender = os.environ.get('SMTP_USER', '')
    app_name = 'Easy OKAPI'

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'Verify your {app_name} account'
    msg['From'] = f'{app_name} <{sender}>'
    msg['To'] = to_email

    text_body = (
        f"Hi {name},\n\n"
        f"Thank you for registering for {app_name}.\n\n"
        f"Please verify your email by visiting:\n{verify_url}\n\n"
        f"This link expires in 24 hours.\n\n"
        f"If you did not create this account, you can ignore this email.\n\n"
        f"— The {app_name} Team"
    )
    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:0">
  <div style="max-width:520px;margin:40px auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.1)">
    <div style="background:#2d6a4f;padding:28px 32px">
      <h1 style="color:#fff;margin:0;font-size:22px">{app_name}</h1>
    </div>
    <div style="padding:32px">
      <p style="font-size:16px;color:#333">Hi <strong>{name}</strong>,</p>
      <p style="font-size:15px;color:#555">Thank you for registering. Please verify your email address to activate your account and download the app.</p>
      <div style="text-align:center;margin:32px 0">
        <a href="{verify_url}" style="background:#2d6a4f;color:#fff;padding:12px 28px;border-radius:6px;text-decoration:none;font-size:15px;font-weight:bold">Verify Email Address</a>
      </div>
      <p style="font-size:13px;color:#999">This link expires in <strong>24 hours</strong>. If you did not create this account, you can safely ignore this email.</p>
    </div>
    <div style="background:#f0f0f0;padding:16px 32px;text-align:center">
      <p style="font-size:12px;color:#aaa;margin:0">&copy; Easy OKAPI — Colorimeter Data Visualizer</p>
    </div>
  </div>
</body>
</html>"""

    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    server, _ = _smtp_connection()
    try:
        server.sendmail(sender, [to_email], msg.as_string())
    finally:
        server.quit()
