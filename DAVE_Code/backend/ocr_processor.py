import pytesseract
from PIL import Image
import os
import fitz  # PyMuPDF

pytesseract.pytesseract.tesseract_cmd = r"C:\Users\T00228949\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

def extract_text(image_path):
    
    #Extract text from image or PDF using Tesseract OCR
    #Parameters: image_path (str or Path): Path to the image or PDF file
    #Returns: str: Extracted text from the image/PDF
        
    
    image_path = str(image_path)
    
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"File not found: {image_path}")
    
    try:
        if image_path.lower().endswith('.pdf'):
            return extract_text_from_pdf(image_path)
        
        image = Image.open(image_path)
        
        if image.mode != 'RGB':
            image = image.convert('RGB')
 
        grayscale_image = image.convert('L')
        
        text = pytesseract.image_to_string(grayscale_image)
        
        return text
        
    except Exception as e:
        raise Exception(f"OCR processing failed: {str(e)}")

def extract_text_from_pdf(pdf_path):

    #Extract text from PDF file
    #Parameters: pdf_path (str): Path to the PDF file
    #Returns: str: Extracted text from all pages

    try:

        doc = fitz.open(pdf_path)
        text = ""

        for page_num in range(len(doc)):
            page = doc[page_num]
            text += page.get_text()
            
            if not text.strip():

                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) 
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                grayscale_image = img.convert('L')
                text += pytesseract.image_to_string(grayscale_image)
        
        doc.close()
        return text
        
    except Exception as e:
        raise Exception(f"PDF processing failed: {str(e)}")

def extract_text_with_confidence(image_path):

    """Extract text with confidence scores (for future enhancement)
    Parameters: image_path (str): Path to the image file 
    Returns: dict: Dictionary with text and confidence data
    """
    
    try:
        image = Image.open(image_path)
        
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        grayscale_image = image.convert('L')
        
        data = pytesseract.image_to_data(grayscale_image, output_type=pytesseract.Output.DICT)
        
        filtered_text = []
        for i, conf in enumerate(data['conf']):
            if int(conf) > 60:
                filtered_text.append(data['text'][i])
        
        return {
            'text': ' '.join(filtered_text),
            'raw_data': data
        }
        
    except Exception as e:
        raise Exception(f"OCR processing with confidence failed: {str(e)}")

