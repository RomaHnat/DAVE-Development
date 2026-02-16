import uvicorn
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    print("Starting DAVE Backend Server...")
    print("Server will be available at: http://localhost:8000")
    print("API Documentation at: http://localhost:8000/docs")
    print("Auth endpoints at: http://localhost:8000/api/auth")
    
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
