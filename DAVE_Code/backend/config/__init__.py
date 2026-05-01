import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME", "dave_db")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me")
