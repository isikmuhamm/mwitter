import imaplib
import email
import json
import base64
from email.header import decode_header
import quopri
from email.utils import parseaddr
import logging
from pathlib import Path

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config():
    config_path = Path("config.json")
    if not config_path.exists():
        raise FileNotFoundError("config.json dosyası bulunamadı!")
    
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def decode_str(s, default_charset='utf-8'):
    if isinstance(s, str):
        return s
    elif s is None:
        return ''
    
    charsets = [default_charset, 'utf-8', 'iso-8859-9', 'latin-1', 'cp1254', 'ascii']
    for charset in charsets:
        try:
            return s.decode(charset)
        except (UnicodeDecodeError, AttributeError):
            continue
    
    return s.decode('utf-8', errors='ignore')

def decode_mime_words(s):
    if not s:
        return ''
    return ''.join(
        decode_str(word, charset or 'utf-8')
        for word, charset in decode_header(s)
    )

def decode_subject(msg):
    try:
        subject = decode_mime_words(msg.get("Subject", ""))
        return subject
    except Exception as e:
        logger.error(f"Konu çözümlenirken hata oluştu: {e}")
        return "Konu çözümlenemedi"

def decode_from(msg):
    try:
        from_header = msg.get("From", "")
        if not from_header:
            return "Gönderen bilgisi yok"
        
        from_str = decode_mime_words(from_header)
        
        name, email_addr = parseaddr(from_str)
        if name:
            return f"{name} <{email_addr}>"
        return email_addr
    except Exception as e:
        logger.error(f"Gönderen bilgisi çözümlenirken hata oluştu: {e}")
        return "Gönderen bilgisi çözümlenemedi"

def get_mail_content(msg):
    text_content = []
    html_content = []
    attachments = []
    
    def extract_content(part):
        try:
            content = part.get_payload(decode=True)
            charset = part.get_content_charset() or 'utf-8'
            
            if content is None:
                return

            if part.get('Content-Transfer-Encoding', '').lower() == 'quoted-printable':
                content = quopri.decodestring(content)
            elif part.get('Content-Transfer-Encoding', '').lower() == 'base64':
                content = base64.b64decode(content)
            
            decoded_content = decode_str(content, charset)
            
            if part.get_content_type() == 'text/plain':
                text_content.append(decoded_content)
            elif part.get_content_type() == 'text/html':
                html_content.append(decoded_content)
            elif part.get_filename():
                attachments.append((part.get_filename(), content))
        except Exception as e:
            logger.error(f"İçerik çözümlenirken hata oluştu: {e}")
            logger.error(f"Hatalı içerik: {content[:100] if content else 'Boş içerik'}...")
    
    if msg.is_multipart():
        for part in msg.walk():
            extract_content(part)
    else:
        extract_content(msg)
    
    return text_content, html_content, attachments

def fetch_email(uid, mail):
    try:
        status, msg_data = mail.uid('fetch', uid.encode(), '(RFC822)')
        if status != 'OK':
            logger.warning(f"Mail ID {uid} için veri alınamadı")
            return None

        email_body = msg_data[0][1]
        msg = email.message_from_bytes(email_body)

        from_ = decode_from(msg)
        to_ = msg.get("To", "")
        date = msg.get("Date", "")
        subject = decode_subject(msg)
        
        text_contents, html_contents, attachments = get_mail_content(msg)

        return {
            'from': from_,
            'to': to_,
            'date': date,
            'subject': subject,
            'text_contents': text_contents,
            'html_contents': html_contents,
            'attachments': attachments,
            'raw_content': email_body
        }
    except Exception as e:
        logger.error(f"E-posta alınırken hata oluştu (UID: {uid}): {e}")
        return None

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

def save_processed_content(uid, email_data):
    try:
        content_dir = Path("content")
        content_dir.mkdir(exist_ok=True)
        
        file_path = content_dir / f"{uid}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump({
                'from': email_data['from'],
                'to': email_data['to'],
                'date': email_data['date'],
                'subject': email_data['subject'],
                'text_contents': email_data['text_contents'],
                'html_contents': email_data['html_contents'],
                'attachments': [name for name, _ in email_data['attachments']]
            }, f, ensure_ascii=False, indent=2)
        
        logger.info(f"İşlenmiş içerik kaydedildi: {file_path}")
    except Exception as e:
        logger.error(f"İşlenmiş içerik kaydedilirken hata oluştu: {e}")

def main():
    try:
        config = load_config()
        
        mail = imaplib.IMAP4_SSL(config["imap_server"])
        mail.login(config["email"], config["password"])
        
        mail.select("inbox")

        processed_mails_file = config["processed_mails_file"]
        with open(processed_mails_file, "r") as f:
            mail_uids = f.read().splitlines()

        for uid in mail_uids:
            if not uid.strip():  # Boş UID'leri atla
                logger.warning("Boş UID atlanıyor.")
                continue

            logger.info(f"\nUID {uid} işleniyor...")
            email_data = fetch_email(uid, mail)
            if email_data:
                logger.info(f"Gönderen: {email_data['from']}")
                logger.info(f"Alıcı: {email_data['to']}")
                logger.info(f"Konu: {email_data['subject']}")
                logger.info(f"Tarih: {email_data['date']}")
                logger.info(f"Metin içeriği sayısı: {len(email_data['text_contents'])}")
                logger.info(f"HTML içeriği sayısı: {len(email_data['html_contents'])}")
                logger.info(f"Ek sayısı: {len(email_data['attachments'])}")
                
                save_raw_content(uid, email_data['raw_content'])
                save_processed_content(uid, email_data)
            else:
                logger.warning(f"UID {uid} için e-posta alınamadı veya işlenemedi.")
            
            logger.info("-" * 100)

    except Exception as e:
        logger.error(f"Ana işlem sırasında hata oluştu: {e}")
    finally:
        try:
            mail.logout()
        except:
            pass

if __name__ == "__main__":
    main()