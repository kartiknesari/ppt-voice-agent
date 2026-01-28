import os
from supabase import create_client
from dotenv import load_dotenv
from ..config import SUPABASE_URL, SUPABASE_SERVICE_KEY

# Load environment variables from the .env file for local development
load_dotenv()

if not SUPABASE_URL:
    raise ValueError("GEMINI_API_KEY is missing. Check your .env file.")
# Initialize the Supabase Client
# SUPABASE_URL: The unique endpoint for your project.
# SUPABASE_SERVICE_KEY: The secret key that allows the backend to bypass Row Level Security.
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
