import asyncio
import logging

logger = logging.getLogger("avatar-safety")


async def keep_alive(ctx):
    """
    Keeps the agent process running until the user disconnects
    or the room is empty.
    """
    logger.info("Agent entering keep_alive state...")
    try:
        # Loop indefinitely until the context is cancelled
        while True:
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        logger.info("Keep_alive cancelled. Cleaning up agent...")
