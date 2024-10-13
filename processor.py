import os
import io
import json
import email
import base64
import quopri
import hashlib
import logging
from PIL import Image
from pathlib import Path
from email.header import decode_header
from email.utils import parseaddr
from pdf2image import convert_from_path

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

def save_processed_uid(uid, config):
    # İşlenmiş UID'leri tek satırda almak için ayar
    processed_uids = config.get("processed_uids", "")
    
    # UID'leri virgülle ayırarak bir listeye çevir
    uid_list = processed_uids.split(",") if processed_uids else []

    if uid not in uid_list:
        uid_list.append(uid)

    # UID'leri tekrar tek satırda birleştir ve config'e kaydet
    config["processed_uids"] = ",".join(uid_list)
    save_config(config)

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

class ImageProcessor:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.processed_hashes = {}
        
    def calculate_image_hash(self, image_data: bytes) -> str:
        return hashlib.md5(image_data).hexdigest()
    
    def process_single_image(self, image_data: bytes, uid: str, index: int, prefix: str):
        image_hash = self.calculate_image_hash(image_data)
        
        if image_hash in self.processed_hashes:
            logger.info(f"Bu resim daha önce kaydedilmiş: {self.processed_hashes[image_hash]}")
            return self.processed_hashes[image_hash]
            
        try:
            img = Image.open(io.BytesIO(image_data))
            output_path = os.path.join(self.output_dir, f"{uid}_{prefix}{index}.jpg")
            
            if img.format != 'JPEG':
                img = img.convert('RGB')
            img.save(output_path, 'JPEG')
            
            self.processed_hashes[image_hash] = output_path
            return output_path
            
        except Exception as e:
            logger.error(f"Resim işlenirken hata oluştu: {e}")
            return None
    
    def process_images(self, images, uid: str, prefix: str = ''):
        processed_files = []
        
        for i, image_data in enumerate(images):
            file_path = self.process_single_image(image_data, uid, i, prefix)
            if file_path:
                processed_files.append(file_path)
                
        return processed_files

    def process_pdf(self, file_path: str, uid: str):
        try:

            poppler_path = config.get("poppler_path", "")
            images = convert_from_path(file_path, first_page=1, last_page=4)
            processed_files = []
            
            for i, image in enumerate(images):
                img_buffer = io.BytesIO()
                image.save(img_buffer, format='JPEG')
                img_data = img_buffer.getvalue()
                
                file_path = self.process_single_image(img_data, uid, i, 'pdf_')
                if file_path:
                    processed_files.append(file_path)
            
            return processed_files
            
        except PDFInfoNotInstalledError:
            logger.error("Poppler yüklü değil veya PATH'te bulunamıyor.")
        except Exception as e:
            logger.error(f"PDF işlenirken hata oluştu: {e}")
        return []

def process_email_content(uid, output_dir):
    raw_content_dir = Path("rawcontent")
    raw_content_path = raw_content_dir / f"{uid}.eml"
    
    if not raw_content_path.exists():
        logger.warning(f"Ham içerik bulunamadı: {raw_content_path}")
        return []
    
    with open(raw_content_path, 'rb') as f:
        raw_content = f.read()
    
    msg = email.message_from_bytes(raw_content)
    image_processor = ImageProcessor(output_dir)
    processed_files = []
    
    from_ = decode_from(msg)
    to_ = msg.get("To", "")
    date = msg.get("Date", "")
    subject = decode_subject(msg)
    
    text_contents, html_contents, attachments = get_mail_content(msg)
    
    # Process images and PDFs
    for part in msg.walk():
        if part.get_content_maintype() == 'image':
            content = part.get_payload(decode=True)
            processed_file = image_processor.process_single_image(content, uid, len(processed_files), 'img_')
            if processed_file:
                processed_files.append(processed_file)
        elif part.get_filename() and part.get_filename().lower().endswith('.pdf'):
            temp_pdf_path = os.path.join(output_dir, f"temp_{part.get_filename()}")
            with open(temp_pdf_path, 'wb') as f:
                f.write(part.get_payload(decode=True))
            processed_files.extend(image_processor.process_pdf(temp_pdf_path, uid))
            os.remove(temp_pdf_path)
    
    # Save processed content as JSON
    content_dir = Path(output_dir)
    content_dir.mkdir(exist_ok=True)
    
    json_file_path = content_dir / f"{uid}.json"
    with open(json_file_path, "w", encoding="utf-8") as f:
        json.dump({
            'from': from_,
            'to': to_,
            'date': date,
            'subject': subject,
            'text_contents': text_contents,
            'html_contents': html_contents,
            'attachments': [name for name, _ in attachments],
            'processed_files': processed_files
        }, f, ensure_ascii=False, indent=2)
    
    logger.info(f"İşlenmiş içerik kaydedildi: {json_file_path}")
    return processed_files

def main():
    try:
        config = load_config()
        output_dir = "content"
        os.makedirs(output_dir, exist_ok=True)

        mail_uids = config.get("collected_uids", "").split(",")

        for uid in mail_uids:
            if not uid.strip():
                logger.warning("Boş UID atlanıyor.")
                continue

            logger.info(f"UID {uid} işleniyor...")
            processed_files = process_email_content(uid, output_dir)
            if processed_files:
                logger.info(f"İşlenmiş dosyalar: {', '.join(processed_files)}")
                save_processed_uid(uid, config)
            else:
                logger.warning(f"UID {uid} için ek dosya bulunmadığından işlem yapılamadı.")
            
            logger.info("-" * 100)

    except Exception as e:
        logger.error(f"Ana işlem sırasında hata oluştu: {e}")

if __name__ == "__main__":
    main()