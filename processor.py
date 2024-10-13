import os
from PIL import Image
import io
import hashlib
import logging
from pdf2image import convert_from_path

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
            
        except Exception as e:
            logger.error(f"PDF işlenirken hata oluştu: {e}")
            return []

def process_email_content(email_data, output_dir):
    image_processor = ImageProcessor(output_dir)
    
    processed_files = []
    
    # HTML içeriğinden gömülü resimleri çıkar
    for html_content in email_data['html_contents']:
        # Base64 kodlu resimleri bul ve işle
        # Bu kısmı implement etmeniz gerekecek
        pass
    
    # Ekleri işle
    for attachment_name, attachment_data in email_data['attachments']:
        if attachment_name.lower().endswith('.pdf'):
            # PDF'i geçici bir dosyaya kaydet ve işle
            temp_pdf_path = os.path.join(output_dir, f"temp_{attachment_name}")
            with open(temp_pdf_path, 'wb') as f:
                f.write(attachment_data)
            processed_files.extend(image_processor.process_pdf(temp_pdf_path, email_data['uid']))
            os.remove(temp_pdf_path)
        elif attachment_name.lower().endswith(('.jpg', '.jpeg', '.png')):
            file_path = image_processor.process_single_image(attachment_data, email_data['uid'], 0, 'attach_')
            if file_path:
                processed_files.append(file_path)
    
    return processed_files

def main():
    # Bu fonksiyon, contenthunter.py'den gelen verileri işleyecek
    # Örnek kullanım:
    # email_data = contenthunter.fetch_email(uid, mail)
    # processed_files = process_email_content(email_data, 'output_directory')
    pass

if __name__ == "__main__":
    main()