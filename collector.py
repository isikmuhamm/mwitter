import imaplib
import email
import json
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config():
    config_path = Path("config.json")
    if not config_path.exists():
        raise FileNotFoundError("config.json dosyası bulunamadı!")
    
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config):
    config_path = Path("config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

def save_raw_content(uid, raw_content):
    try:
        raw_content_dir = Path("rawcontent")
        raw_content_dir.mkdir(exist_ok=True)
        
        file_path = raw_content_dir / f"{uid}.eml"
        with open(file_path, "wb") as f:
            f.write(raw_content)
        
        logger.info(f"Ham içerik kaydedildi: {file_path}")
    except Exception as e:
        logger.error(f"Ham içerik kaydedilirken hata oluştu: {e}")

def is_personal_email(msg, user_email):
    to_ = msg.get("To", "")
    cc_ = msg.get("Cc", "")
    bcc_ = msg.get("Bcc", "")
    return (user_email in to_ or "undisclosed-recipients" in to_ or
            user_email in cc_ or user_email in bcc_ or to_ is None or to_ == "")

def collect_unread_mails(mail, config):
    mail.select("inbox")
    status, messages = mail.uid('search', None, "UNSEEN")
    mail_ids = messages[0].split()

    new_mails = []

    # Collected UID'leri tek satırda almak için ayar
    collected_uids = config.get("collected_uids", "").split(",")

    for mail_id in mail_ids:
        mail_id_str = mail_id.decode()

        if mail_id_str in collected_uids:
            mail.uid('STORE', mail_id, '+FLAGS', '\\Seen')
            continue

        status, msg_data = mail.uid('fetch', mail_id, '(BODY.PEEK[])')
        if status != 'OK':
            logger.warning(f"Mail ID {mail_id_str} için veri alınamadı")
            continue

        email_body = msg_data[0][1]
        msg = email.message_from_bytes(email_body)

        if is_personal_email(msg, config["email"]):
            continue

        new_mails.append(mail_id_str)

        # UID'yi config.json içine ekle (tek satır)
        if collected_uids == [""]:
            collected_uids = [mail_id_str]
        else:
            collected_uids.append(mail_id_str)

        config["collected_uids"] = ",".join(collected_uids)
        save_config(config)

        # Ham içeriği kaydet
        save_raw_content(mail_id_str, email_body)

        mail.uid('STORE', mail_id, '+FLAGS', '\\Seen')

    return new_mails


def main():
    try:
        config = load_config()
        mail = imaplib.IMAP4_SSL(config["imap_server"])
        mail.login(config["email"], config["password"])

        new_mails = collect_unread_mails(mail, config)

        if new_mails:
            logger.info(f"Yeni duyuru mailleri: {', '.join(new_mails)}")
        else:
            logger.info("Yeni duyuru maili bulunamadı.")

    except Exception as e:
        logger.error(f"Hata oluştu: {e}")
    
    finally:
        try:
            mail.logout()
        except:
            pass

if __name__ == "__main__":
    main()
