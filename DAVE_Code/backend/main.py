from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
import os
import shutil
from datetime import datetime
import uuid
from pathlib import Path

from backend.database import connect_to_mongo, close_mongo_connection
from backend.routes import auth, users, admin
from backend.ocr_processor import extract_text
from backend.date_validator import find_expiry_date, validate_document

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connect to MongoDB
    await connect_to_mongo()
    print("Connected to MongoDB")
    yield
    # Shutdown: Close MongoDB connection
    await close_mongo_connection()
    print("Disconnected from MongoDB")

app = FastAPI(
    title="DAVE - Documents and Applications Validation Engine",
    version="1.0.0",
    description="Full-stack application for document validation and application management",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api")
app.include_router(admin.router, prefix="/api")

class ProcessRequest(BaseModel):
    filename: str

class UploadResponse(BaseModel):
    filename: str
    upload_time: str
    status: str
    message: str

class ProcessResponse(BaseModel):
    extracted_text: str
    expiry_date: str
    is_valid: bool
    days_remaining: int
    processing_time: float
    status: str

@app.get("/")
def root():
    return {
        "message": "DAVE - Documents and Applications Validation Engine",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "auth": "/api/auth",
            "upload": "POST /api/upload",
            "process": "POST /api/process"
        }
    }

@app.post("/api/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):

    #Upload ID document endpoint
    #Accepts: JPG, JPEG, PNG, PDF files (max 6MB)
    #Returns: filename, upload_time, status
    
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "application/pdf"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: JPG, PNG, PDF. Got: {file.content_type}"
        )
    
    file_content = await file.read()
    file_size = len(file_content)
    
    max_size = 6 * 1024 * 1024  
    if file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is 6MB. Got: {file_size / (1024 * 1024):.2f}MB"
        )
    
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = UPLOADS_DIR / unique_filename
    
    try:
        with open(file_path, "wb") as f:
            f.write(file_content)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save file: {str(e)}"
        )
    
    return UploadResponse(
        filename=unique_filename,
        upload_time=datetime.now().isoformat(),
        status="success",
        message=f"File uploaded successfully: {file.filename}"
    )

@app.post("/api/process", response_model=ProcessResponse)
async def process_document(request: ProcessRequest):
    
    """Process document with OCR and validate expiry date
    Parameters: request (ProcessRequest): Request containing the filename
    Returns: ProcessResponse: Response containing extracted text, expiry date, validity, and days remaining
    """
    
    file_path = UPLOADS_DIR / request.filename
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {request.filename}"
        )
    
    start_time = datetime.now()
    
    try:
        extracted_text = extract_text(file_path)
        
        if not extracted_text or len(extracted_text.strip()) == 0:
            raise HTTPException(
                status_code=422,
                detail="No text could be extracted from the document. Please ensure the image is clear and readable."
            )
        
        expiry_date = find_expiry_date(extracted_text)
        
        validation_result = validate_document(expiry_date)
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return ProcessResponse(
            extracted_text=extracted_text.strip(),
            expiry_date=expiry_date if expiry_date else "Not detected",
            is_valid=validation_result["is_valid"],
            days_remaining=validation_result["days_remaining"],
            processing_time=processing_time,
            status="success"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
