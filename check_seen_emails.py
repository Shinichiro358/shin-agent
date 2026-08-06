#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import imaplib
import email
from email.header import decode_header
from datetime import datetime
import os
import re
from pathlib import Path
from dotenv import load_dotenv

# .env ファイルを読み込む
load_dotenv(dotenv_path=r'C:\shin-agent\.env')

IMAP_SERVER = os.getenv('IMAP_SERVER')
IMAP_PORT = int(os.getenv('IMAP_PORT', 993))
IMAP_USER = os.getenv('IMAP_USER')
IMAP_PASSWORD = os.getenv('IMAP_PASSWORD')
IMAP_FOLDER = os.getenv('IMAP_FOLDER', 'INBOX')

def decode_subject(subject):
    """メールの件名をデコード"""
    if subject is None:
        return ""
    decoded_parts = []
    for part, charset in decode_header(subject):
        if isinstance(part, bytes):
            try:
                decoded_parts.append(part.decode(charset or 'utf-8', errors='ignore'))
            except:
                decoded_parts.append(part.decode('utf-8', errors='ignore'))
        else:
            decoded_parts.append(part)
    return ''.join(decoded_parts)

def get_sender(msg):
    """メールの差出人を取得"""
    sender = msg.get('From', '')
    if not sender:
        return ""
    # メールアドレスを抽出
    match = re.search(r'<(.+?)>', sender)
    if match:
        return match.group(1)
    return sender.split(',')[0].strip()

def get_date(msg):
    """メール日時を取得"""
    return msg.get('Date', '')

def get_body_text(msg, limit=300):
    """メール本文を取得（最初の300文字）"""
    body = ""

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    body = part.get_payload(decode=True).decode(charset, errors='ignore')
                    break
                except:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        except:
            body = msg.get_payload()

    # 引用部分を除外
    lines = []
    for line in body.split('\n'):
        if not line.startswith('>'):
            lines.append(line)

    body = '\n'.join(lines).strip()
    return body[:limit]

def connect_imap():
    """IMAP接続"""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASSWORD)
        return mail
    except Exception as e:
        raise Exception(f"メールサーバーに接続できません: {str(e)}")

def fetch_seen_emails(limit=20):
    """既読メール取得"""
    mail = connect_imap()

    try:
        mail.select(IMAP_FOLDER)
        # 既読（SEEN）メールを取得。最新の limit 件
        status, messages = mail.search(None, 'SEEN')

        if status != 'OK':
            return []

        msg_ids = messages[0].split()
        # 最新の limit 件のみ取得
        msg_ids = msg_ids[-limit:] if len(msg_ids) > limit else msg_ids

        emails_data = []

        for msg_id in msg_ids:
            status, msg_data = mail.fetch(msg_id, '(RFC822)')
            if status == 'OK':
                msg = email.message_from_bytes(msg_data[0][1])
                emails_data.append({
                    'msg_id': msg_id,
                    'msg': msg,
                    'date': get_date(msg),
                    'subject': decode_subject(msg.get('Subject', '')),
                    'sender': get_sender(msg),
                    'body': get_body_text(msg, 150),
                })

        # 日時でソート（新しい順）
        emails_data.reverse()

        return emails_data

    finally:
        mail.close()
        mail.logout()

def main():
    print("既読メール取得中...")

    try:
        emails = fetch_seen_emails(limit=20)
    except Exception as e:
        print(f"エラー: {e}")
        return

    print(f"\n取得しました: {len(emails)}件（直近20件）")
    print("="*80)

    for i, email_data in enumerate(emails, 1):
        print(f"\n{i}. [{email_data['date']}]")
        print(f"   差出人：{email_data['sender']}")
        print(f"   件名：{email_data['subject']}")
        if email_data['body']:
            print(f"   要点：{email_data['body'][:100]}...")

if __name__ == '__main__':
    main()
