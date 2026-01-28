from livekit.plugins import anam, simli
from ..config import ANAM_API_KEY, ANAM_AVATAR_ID, SIMLI_API_KEY, SIMLI_FACE_ID


def create_avatar():
    return simli.AvatarSession(
        simli_config=simli.SimliConfig(api_key=SIMLI_API_KEY, face_id=SIMLI_FACE_ID),
    )
    # return anam.AvatarSession(
    #     persona_config=anam.PersonaConfig(name="Dia", avatarId=ANAM_AVATAR_ID),
    #     api_key=ANAM_API_KEY,
    #     api_url="https://api.anam.ai",
    # )
