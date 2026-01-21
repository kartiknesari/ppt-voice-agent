# app/llm/gemini.py
from livekit.plugins import google, openai
from config import GEMINI_API_KEY, OPENAI_API_KEY
from avatar.persona import SYSTEM_INSTRUCTIONS


def create_llm():
    """
    Creates and configures the Gemini Realtime Model for voice conversations.
    """
    if not OPENAI_API_KEY:
        raise ValueError("OPEN_API_KEY is missing. Check your .env file.")
    return openai.realtime.RealtimeModel(voice="alloy")

    # if not GEMINI_API_KEY:
    # raise ValueError("GEMINI_API_KEY is missing. Check your .env file.")
    # # FIXED: Use the correct import path - google.realtime.RealtimeModel
    # return google.realtime.RealtimeModel(
    #     model="gemini-2.5-flash-native-audio-preview-09-2025",
    #     api_key=GEMINI_API_KEY,
    #     voice="Aoede",
    #     instructions=SYSTEM_INSTRUCTIONS,
    #     temperature=0.6,
    # )
