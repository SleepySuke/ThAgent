# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-17 14:29:17
@Description：
邮件客户端 — IMAP 收件 + SMTP 发件（163邮箱）
'''

import imaplib
import smtplib
import email
from email.header import decode_header
from email.mime.text import MIMEText

# 163 邮箱要求登录后发送 IMAP ID 命令，否则 SELECT 会被拒绝
imaplib.Commands["ID"] = "AUTH"


# ── IMAP 收件 ─────────────────────────────────────────

def fetch_emails(imap_server: str, email_address: str, auth_code: str):
    """连接到163邮箱并获取未读邮件"""
    if not email_address or not auth_code:
        return

    try:
        mail = imaplib.IMAP4_SSL(imap_server, 993)
    except imaplib.IMAP4.error as e:
        raise ConnectionError(f"IMAP 连接失败: {e}")

    try:
        mail.login(email_address, auth_code)
    except imaplib.IMAP4.error as e:
        mail.logout()
        raise ConnectionError(f"IMAP 登录失败: {e}")

    # 163 要求发送 IMAP ID 表明客户端身份，否则 SELECT 被拒绝
    id_args = '("name" "email-agent" "version" "1.0" "vendor" "langgraph" "contact" "%s")' % email_address
    mail._simple_command("ID", id_args)

    status, data = mail.select('INBOX')
    if status != 'OK':
        server_msg = data[0].decode() if data else 'unknown'
        mail.logout()
        raise ConnectionError(f"IMAP 选择收件箱失败: {server_msg}")

    try:
        status, messages = mail.search(None, 'UNSEEN')
        if status != 'OK' or not messages[0]:
            return

        for msg_id in messages[0].split():
            try:
                status, msg_data = mail.fetch(msg_id, '(RFC822)')
                if status != 'OK':
                    continue

                raw_email = msg_data[0][1]
                email_message = email.message_from_bytes(raw_email)

                subject, encoding = decode_header(email_message['Subject'])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding if encoding else 'utf-8')

                from_ = email.utils.parseaddr(email_message['From'])[1]
                body = _extract_body(email_message)

                yield {
                    "email_id": msg_id.decode(),
                    "sender_email": from_,
                    "email_content": body,
                    "email_subject": subject,
                }
            except Exception:
                continue
    finally:
        mail.close()
        mail.logout()


def _extract_body(email_message) -> str:
    """从邮件中提取纯文本正文"""
    if email_message.is_multipart():
        for part in email_message.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get('Content-Disposition'))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode('utf-8', errors='ignore')
        return ""
    payload = email_message.get_payload(decode=True)
    if payload:
        return payload.decode('utf-8', errors='ignore')
    return ""


# ── SMTP 发件 ─────────────────────────────────────────

def send_email(
    smtp_server: str,
    email_address: str,
    auth_code: str,
    to: str,
    subject: str,
    body: str,
) -> bool:
    """通过 SMTP 发送邮件"""
    if not email_address or not auth_code or not to:
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = email_address
    msg["To"] = to
    msg["Subject"] = subject

    try:
        server = smtplib.SMTP_SSL(smtp_server, 465)
        server.login(email_address, auth_code)
        server.sendmail(email_address, [to], msg.as_string())
        server.quit()
        return True
    except smtplib.SMTPException as e:
        raise ConnectionError(f"SMTP 发送失败: {e}")
