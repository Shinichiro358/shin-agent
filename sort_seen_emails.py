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

def get_to(msg):
    """メールの宛先を取得"""
    to = msg.get('To', '')
    if not to:
        return ""
    # メールアドレスを抽出
    match = re.search(r'<(.+?)>', to)
    if match:
        return match.group(1)
    return to.split(',')[0].strip()

def is_target_recipient(msg):
    """宛先がhayashi@mino-ex.co.jpか確認"""
    to = msg.get('To', '')
    if not to:
        return False
    return 'hayashi@mino-ex.co.jp' in to

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

def check_unsubscribe(msg):
    """配信停止リンクの有無を確認"""
    body = get_body_text(msg, limit=10000)
    sender = get_sender(msg)
    subject = decode_subject(msg.get('Subject', ''))

    # 配信停止キーワード
    unsubscribe_keywords = ['配信停止', '購読解除', 'unsubscribe', '配信を停止', 'リスト削除']
    if any(kw in body for kw in unsubscribe_keywords):
        return True

    # no-reply 系のアドレス
    noreply_patterns = ['no-reply', 'noreply', 'newsletter', 'info@', 'news@']
    if any(re.search(pattern, sender, re.IGNORECASE) for pattern in noreply_patterns):
        return True

    # メルマガ系の特性
    magazine_keywords = ['news', 'magazine', 'mail', 'letter', '配信', 'メール', 'セミナー', '招待', 'webinar', 'event']
    if any(kw in subject.lower() or kw in sender.lower() for kw in magazine_keywords):
        # ドメインで確認（ma.などのメール配信サービス）
        if 'ma.' in sender or 'mail' in sender or '.sbcr.jp' in sender or 'president.jp' in sender or 'event-bit' in sender:
            return True

    return False

def check_auto_notification(subject):
    """システム自動通知のパターンマッチ"""
    patterns = [
        r'受注確認',
        r'納期回答',
        r'在庫アラート',
        r'配送完了',
        r'注文確認',
        r'請求書',
        r'発送通知',
    ]
    return any(re.search(p, subject) for p in patterns)

def is_business_related(subject, body, sender):
    """本業関連かどうかを判定"""
    # 仕入先ドメイン
    supplier_domains = [
        'olander.com',
        'okuno.co.jp',
    ]

    # 仕入先からのメール
    if any(domain in sender for domain in supplier_domains):
        return True

    # キーワード検索
    business_keywords = [
        '見積',
        '価格',
        '納期',
        '在庫',
        '商品',
        '発注',
        '受注',
        'SDS',
        'EKC',
        'Qnity',
        'Dipsol',
        'めっき',
        '表面処理',
        '非鉄',
        'チラー',
        'ポンプ',
        'フィルタープレス',
    ]

    text = f"{subject} {body}"
    return any(kw in text for kw in business_keywords)

def connect_imap():
    """IMAP接続"""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASSWORD)
        return mail
    except Exception as e:
        raise Exception(f"メールサーバーに接続できません: {str(e)}")

def fetch_seen_emails(limit=10):
    """既読メール取得"""
    mail = connect_imap()

    try:
        mail.select(IMAP_FOLDER)
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
                # 宛先がhayashi@mino-ex.co.jpのみを対象
                if is_target_recipient(msg):
                    emails_data.append({
                        'msg_id': msg_id,
                        'msg': msg,
                        'subject': decode_subject(msg.get('Subject', '')),
                        'sender': get_sender(msg),
                        'body': get_body_text(msg),
                    })

        # 日時でソート（新しい順）
        emails_data.reverse()

        return emails_data

    finally:
        mail.close()
        mail.logout()

def sort_emails(emails):
    """メール仕分け"""
    excluded = []
    auto_notifications = []
    business = []
    non_business = []

    for email_data in emails:
        subject = email_data['subject']
        sender = email_data['sender']
        body = email_data['body']

        # ふるい1: 配信停止系
        if check_unsubscribe(email_data['msg']):
            excluded.append(email_data)
            continue

        # ふるい2: 自動通知
        if check_auto_notification(subject):
            auto_notifications.append(email_data)
            continue

        # 本業関連かどうか
        if is_business_related(subject, body, sender):
            business.append(email_data)
        else:
            non_business.append(email_data)

    return excluded, auto_notifications, business, non_business

def main():
    print("既読メール取得中...")

    try:
        emails = fetch_seen_emails(limit=10)
    except Exception as e:
        print(f"エラー: {e}")
        return

    if not emails:
        print("既読メールがありません")
        return

    print(f"取得しました: {len(emails)}件")

    excluded, auto_notifications, business, non_business = sort_emails(emails)

    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    # 結果表示
    print("\n" + "="*60)
    print(f"■ 実行日時：{now}")
    print(f"■ 処理：{len(emails)}通")
    print(f"  除外：{len(excluded)}通 ／ 定型：{len(auto_notifications)}通")
    print(f"  本業関連：{len(business)}通 ／ 業務外：{len(non_business)}通")
    print("="*60)

    if business:
        print("\n【本業関連】")
        for i, email_data in enumerate(business, 1):
            print(f"{i}. {email_data['sender']}")
            print(f"   件名：{email_data['subject']}")

    if non_business:
        print("\n【業務外】")
        for i, email_data in enumerate(non_business, 1):
            print(f"{i}. {email_data['sender']}")
            print(f"   件名：{email_data['subject']}")

    if auto_notifications:
        print("\n【定型通知】")
        for i, email_data in enumerate(auto_notifications, 1):
            print(f"{i}. {email_data['sender']}")
            print(f"   件名：{email_data['subject']}")

    if excluded:
        print(f"\n【除外】{len(excluded)}件")

    # output ディレクトリ作成
    output_dir = Path(r'C:\shin-agent\output')
    output_dir.mkdir(exist_ok=True)

    # ファイル保存
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = output_dir / f"seen_emails_{timestamp}.txt"

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"■ 実行日時：{now}\n")
        f.write(f"■ 処理：{len(emails)}通\n")
        f.write(f"  除外：{len(excluded)}通 ／ 定型：{len(auto_notifications)}通\n")
        f.write(f"  本業関連：{len(business)}通 ／ 業務外：{len(non_business)}通\n\n")

        if business:
            f.write("【本業関連】\n")
            for i, email_data in enumerate(business, 1):
                f.write(f"{i}. {email_data['sender']}\n")
                f.write(f"   件名：{email_data['subject']}\n")

        if non_business:
            f.write("\n【業務外】\n")
            for i, email_data in enumerate(non_business, 1):
                f.write(f"{i}. {email_data['sender']}\n")
                f.write(f"   件名：{email_data['subject']}\n")

        if auto_notifications:
            f.write("\n【定型通知】\n")
            for i, email_data in enumerate(auto_notifications, 1):
                f.write(f"{i}. {email_data['sender']}\n")
                f.write(f"   件名：{email_data['subject']}\n")

        if excluded:
            f.write(f"\n【除外】{len(excluded)}件\n")

    print(f"\n結果を保存しました: {output_file}")

if __name__ == '__main__':
    main()
