# DAVE Prototype

**Documents and Applications Validation Engine**

A web-based application for validating ID documents using OCR technology to extract and verify expiry dates.

## Features

- **Document Upload**: Upload ID documents (JPG, PNG, PDF) up to 6MB
- **OCR Processing**: Extract text from documents using Tesseract OCR
- **Date Validation**: Automatically detect and validate expiry dates
- **User Authentication**: Simple login system for secure access
- **Real-time Feedback**: View extracted text, expiry dates, and validation status

## Prerequisites

- Python 3.8+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed on your system
- Modern web browser

## Installation

1. **Install Tesseract OCR**
   - Download and install from: https://github.com/tesseract-ocr/tesseract
   - Note the installation path (default: `C:\Users\<username>\AppData\Local\Programs\Tesseract-OCR\tesseract.exe`)

2. **Install Python Dependencies**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Configure Tesseract Path**
   - Update the Tesseract path in `backend/ocr_processor.py` if needed:
   ```python
   pytesseract.pytesseract.tesseract_cmd = r"C:\Path\To\tesseract.exe"
   ```

## Usage

1. **Start the Backend Server**
   ```powershell
   python backend/main.py
   ```
   The API will run on `http://localhost:8000`

2. **Open the Frontend**
   - Open `frontend/login.html` in your web browser
   - Login credentials:
     - Email: `test@dave.ie`
     - Password: `test123`

3. **Upload and Process Documents**
   - Select an ID document (JPG, PNG, or PDF)
   - Click "Upload Document"
   - Wait for OCR processing and validation results

## API Endpoints

### `GET /`
Health check and API information

### `POST /api/upload`
Upload an ID document
- **Accepts**: JPG, JPEG, PNG, PDF (max 6MB)
- **Returns**: Upload confirmation with filename and timestamp

### `POST /api/process`
Process uploaded document with OCR
- **Accepts**: `{ "filename": "uploaded_file.jpg" }`
- **Returns**: Extracted text, expiry date, validation status, and days remaining

## Technologies Used

- **Backend**: FastAPI, Python
- **OCR**: Tesseract, Pytesseract, Pillow
- **Frontend**: HTML, CSS, JavaScript, Bootstrap 5
- **PDF Processing**: PyMuPDF (fitz)

## Notes

- Documents are stored in the `uploads/` directory
- Tesseract path must be configured correctly for OCR to work
- The application uses session storage for authentication (demo purposes only)
- Maximum file size: 6MB

## Author

RomerOS © 2025
