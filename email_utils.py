import smtplib
from email.mime.text import MIMEText

def send_email(to_email, subject, message):
    from_email = "prateekact17@gmail.com"       # your Gmail
    app_password = "txtl nkms lsve hoec" # App Password from Google
    msg = MIMEText(message)
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
    server.login(from_email, app_password)
    server.send_message(msg)
    server.quit()
    print(f"Email sent to {to_email}")
