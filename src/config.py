import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Explicitly load the .env file for local development environment
load_dotenv()


@dataclass(frozen=True)
class Config:
    """
    Centralized configuration class with strict validation.
    Ensures all necessary API keys are present before the app runs.
    """

    # LiveKit Settings
    LIVEKIT_URL: str = os.getenv("LIVEKIT_URL", "")
    LIVEKIT_API_KEY: str = os.getenv("LIVEKIT_API_KEY", "")
    LIVEKIT_API_SECRET: str = os.getenv("LIVEKIT_API_SECRET", "")

    # Anam Avatar Settings
    ANAM_API_KEY: str = os.getenv("ANAM_API_KEY", "")
    ANAM_AVATAR_ID: str = os.getenv("ANAM_AVATAR_ID", "")

    SIMLI_API_KEY: str = os.getenv("SIMLI_API_KEY", "")
    SIMLI_FACE_ID: str = os.getenv("SIMLI_FACE_ID", "")

    # LLM Settings
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Supabase Settings (Required for your PPT project)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    BUCKET_IMAGES: str = os.getenv("BUCKET_IMAGES", "slide-images")

    # PPT Processing
    CONVERTAPI_KEY: str = os.getenv("CONVERTAPI_KEY", "")

    def validate(self):
        """
        Checks if any mandatory environment variable is empty.
        If a variable is missing, it raises a helpful error message.
        """
        missing = [k for k, v in self.__dict__.items() if not v]
        if missing:
            raise ValueError(
                f"❌ Missing mandatory environment variables: {', '.join(missing)}"
            )


# 1. Create the configuration instance
_config = Config()


# 2. Validation function to be called at runtime
def validate_config():
    _config.validate()


# 3. Export variables as constants for easy importing in other files
LIVEKIT_URL = _config.LIVEKIT_URL
LIVEKIT_API_KEY = _config.LIVEKIT_API_KEY
LIVEKIT_API_SECRET = _config.LIVEKIT_API_SECRET

ANAM_API_KEY = _config.ANAM_API_KEY
ANAM_AVATAR_ID = _config.ANAM_AVATAR_ID

SIMLI_API_KEY = _config.SIMLI_API_KEY
SIMLI_FACE_ID = _config.SIMLI_FACE_ID

GEMINI_API_KEY = _config.GEMINI_API_KEY
OPENAI_API_KEY = _config.OPENAI_API_KEY

SUPABASE_URL = _config.SUPABASE_URL
SUPABASE_SERVICE_KEY = _config.SUPABASE_SERVICE_KEY
BUCKET_IMAGES = _config.BUCKET_IMAGES

CONVERTAPI_KEY = _config.CONVERTAPI_KEY
