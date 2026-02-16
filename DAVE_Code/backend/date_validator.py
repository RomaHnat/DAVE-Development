import re
from datetime import datetime, timedelta

def find_expiry_date(text):
  
    """Find expiry date in extracted text using regex patterns
    Parameters: text (str): Extracted text from OCR
    Returns: str: Expiry date in DD/MM/YYYY format, or None if not found"""
    
    if not text:
        return None
    
    text_lower = text.lower()
    
    expiry_keywords = [
        'date of expiry', 'expiry date', 'expiry', 'expires', 
        'expiration', 'valid until', 'valid till', 'valid to', 'exp'
    ]
    
    date_patterns = [
        r'\b(\d{2})[\/\-\.\s](\d{2})[\/\-\.\s](\d{4})\b',  # DD/MM/YYYY or DD MM YYYY
        r'\b(\d{1,2})[\/\-\.\s](\d{1,2})[\/\-\.\s](\d{4})\b',  # D/M/YYYY or D M YYYY
        r'\b(\d{4})[\/\-\.\s](\d{2})[\/\-\.\s](\d{2})\b',  # YYYY/MM/DD or YYYY MM DD
    ]
    
    for keyword in expiry_keywords:
        keyword_pos = text_lower.find(keyword)
        if keyword_pos != -1:
            
            text_after_keyword = text[keyword_pos + len(keyword):]
            
            for pattern in date_patterns:
                matches = re.findall(pattern, text_after_keyword)
                if matches:
                    date_tuple = matches[0]
                    try:
                        if len(date_tuple[0]) == 4:  
                            year, month, day = date_tuple
                        else: 
                            day, month, year = date_tuple
                        
                        date_obj = datetime(int(year), int(month), int(day))
                        return f"{int(day):02d}/{int(month):02d}/{year}"
                    except ValueError:
                        continue
    
    return None

def validate_document(expiry_date_str):
    
    """Validate document expiry date against current date
    Parameters: expiry_date_str (str): Expiry date in DD/MM/YYYY format
    Returns:
        dict: {
            'is_valid': bool,
            'days_remaining': int (negative if expired),
            'expiry_date': str
        }"""

    current_date = datetime.now()
    
    if not expiry_date_str or expiry_date_str == "Not detected":
        return {
            'is_valid': False,
            'days_remaining': 0,
            'expiry_date': 'Not detected'
        }
    
    try:
        day, month, year = expiry_date_str.split('/')
        expiry_date = datetime(int(year), int(month), int(day))

        days_diff = (expiry_date - current_date).days

        is_valid = days_diff >= 0
        
        return {
            'is_valid': is_valid,
            'days_remaining': days_diff,
            'expiry_date': expiry_date_str
        }
        
    except Exception as e:
        return {
            'is_valid': False,
            'days_remaining': 0,
            'expiry_date': expiry_date_str,
            'error': str(e)
        }
