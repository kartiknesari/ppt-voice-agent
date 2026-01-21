# agent/main.py
import asyncio
import logging
from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    function_tool,
)
from livekit.agents.voice import VoiceActivityVideoSampler, room_io
from llm.llm import create_llm
from avatar.anam_avatar import create_avatar
from avatar.persona import SYSTEM_INSTRUCTIONS
from utils.safety import keep_alive
from core.supabase import supabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dia-presenter-agent")
logger.setLevel(logging.INFO)

# Global state for navigation tools
current_slide_index = 0
total_slides = 0
slides_data = []
room_context = None


# ==================== NAVIGATION TOOL FUNCTIONS ====================


@function_tool(description="Move to the next slide in the presentation")
async def next_slide():
    """Move to the next slide when user says 'next', 'next slide', or 'move forward'"""
    global current_slide_index, total_slides

    if current_slide_index < total_slides - 1:
        current_slide_index += 1
        await update_slide_display()

        # Get new slide content
        slide = slides_data[current_slide_index]
        content = slide.get("extracted_text", "")

        logger.info(f"✅ Moved to slide {current_slide_index + 1}")
        return (
            f"Now on slide {current_slide_index + 1} of {total_slides}. {content[:100]}"
        )
    else:
        logger.info("Already on last slide")
        return "Already on the last slide"


@function_tool(description="Move to the previous slide in the presentation")
async def previous_slide():
    """Move to the previous slide when user says 'previous', 'back', or 'go back'"""
    global current_slide_index, total_slides

    if current_slide_index > 0:
        current_slide_index -= 1
        await update_slide_display()

        # Get new slide content
        slide = slides_data[current_slide_index]
        content = slide.get("extracted_text", "")

        logger.info(f"✅ Moved to slide {current_slide_index + 1}")
        return (
            f"Now on slide {current_slide_index + 1} of {total_slides}. {content[:100]}"
        )
    else:
        logger.info("Already on first slide")
        return "Already on the first slide"


@function_tool(
    description="Jump to a specific slide number when user says 'go to slide X' or 'show slide X'"
)
async def goto_slide(slide_number: int):
    """
    Jump to a specific slide

    Args:
        slide_number: The slide number to jump to (1-indexed)
    """
    global current_slide_index, total_slides

    if 1 <= slide_number <= total_slides:
        current_slide_index = slide_number - 1
        await update_slide_display()

        # Get new slide content
        slide = slides_data[current_slide_index]
        content = slide.get("extracted_text", "")

        logger.info(f"✅ Jumped to slide {slide_number}")
        return f"Now on slide {slide_number} of {total_slides}. {content[:100]}"
    else:
        logger.warning(f"Invalid slide number: {slide_number}")
        return f"Invalid slide number. Please choose between 1 and {total_slides}"


async def update_slide_display():
    """Update the frontend to show the current slide"""
    global current_slide_index, total_slides, room_context, slides_data

    if room_context is None:
        logger.error("❌ Room context not available")
        return

    try:
        slide = slides_data[current_slide_index]
        await room_context.room.local_participant.set_attributes(
            {
                "current_slide_url": slide.get("image_url", ""),
                "current_slide_number": str(current_slide_index + 1),
                "total_slides": str(total_slides),
            }
        )
        logger.info(
            f"📊 Display updated: Slide {current_slide_index + 1}/{total_slides}"
        )
    except Exception as e:
        logger.error(f"❌ Failed to update display: {e}")


async def entrypoint(ctx: JobContext):
    """
    Core entrypoint for the AI Agent worker.
    """
    global current_slide_index, total_slides, slides_data, room_context

    logger.info(f"🚀 Initializing agent for room: {ctx.room.name}")

    session = None
    avatar = None
    room_context = ctx  # Store context for navigation tools

    try:
        # 1. Connect to room
        await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_ALL)
        logger.info("✅ Successfully connected to LiveKit room.")

        # 2. Get presentation ID from participant metadata
        await asyncio.sleep(2.5)

        presentation_id = None
        for participant in ctx.room.remote_participants.values():
            if participant.metadata:
                presentation_id = participant.metadata
                logger.info(f"✅ Verified Presentation ID: {presentation_id}")
                break

        if not presentation_id:
            logger.error("❌ FATAL: No presentation_id found in metadata.")
            return

        # 3. Load slides from Supabase
        logger.info(f"🔍 Querying slides for: {presentation_id}")
        query_result = (
            supabase.table("slides")
            .select("*")
            .eq("presentation_id", presentation_id)
            .order("slide_number", desc=False)
            .execute()
        )

        slides = query_result.data
        if not slides:
            logger.error(f"❌ No slides found for presentation {presentation_id}")
            return

        # Initialize global slide state
        slides_data = slides
        total_slides = len(slides)
        current_slide_index = 0

        logger.info(f"✅ Loaded {total_slides} slides successfully.")

        # 4. Initialize LLM and Avatar
        llm = create_llm()
        logger.info("✅ Gemini LLM initialized.")

        avatar = create_avatar()
        logger.info("✅ Anam Avatar initialized.")

        # 5. Create Agent Session with navigation tools
        session = AgentSession(
            llm=llm,
            video_sampler=VoiceActivityVideoSampler(speaking_fps=0, silent_fps=0),
            preemptive_generation=False,
            min_endpointing_delay=2.0,
            max_endpointing_delay=5.0,
        )
        logger.info("✅ Agent session configured.")

        # Start avatar
        await avatar.start(session, room=ctx.room)
        logger.info("✅ Anam avatar started.")

        presentation_context = (
            "HERE IS THE FULL PRESENTATION CONTENT YOU ARE PRESENTING:\n"
        )
        for slide in slides:
            s_num = slide.get("slide_number")
            s_text = slide.get("extracted_text", "No text content.")
            presentation_context += f"- Slide {s_num}: {s_text}\n"
        # Build instructions with navigation capabilities
        presenter_instructions = (
            "# System instructions\n"
            f"{SYSTEM_INSTRUCTIONS}\n\n"
            "# Context\n"
            f"{presentation_context}\n\n"
            "#Output Rules\n"
            "ROLE: You are presenting a slide deck to an audience.\n"
            "GOAL: Present each slide's content clearly and engagingly.\n"
            "NAVIGATION: You can control slides using these tools:\n"
            "- next_slide(): Move to the next slide\n"
            "- previous_slide(): Move to the previous slide\n"
            "- goto_slide(N): Jump to slide number N\n"
            "Listen for user commands like 'next', 'previous', 'go to slide 3', etc.\n"
            "STRICT LIMIT: Maximum 4 sentences per response.\n"
            "TONE: Professional, clear, and engaging."
        )

        # Start session with tools
        await session.start(
            agent=Agent(
                instructions=presenter_instructions,
                tools=[next_slide, previous_slide, goto_slide],  # Add navigation tools
            ),
            room=ctx.room,
            room_input_options=room_io.RoomInputOptions(video_enabled=True),
        )
        logger.info("✅ Agent session started with navigation tools.")

        # 6. Present slides automatically
        logger.info("🎬 Starting presentation sequence.")

        while current_slide_index < total_slides:
            slide = slides_data[current_slide_index]
            slide_no = slide.get("slide_number", current_slide_index + 1)
            image_url = slide.get("image_url", "")
            content_text = slide.get("extracted_text", "")

            if not image_url:
                logger.warning(f"⚠️ Slide {slide_no} has no image. Skipping.")
                current_slide_index += 1
                continue

            try:
                # Set attributes for frontend
                await ctx.room.local_participant.set_attributes(
                    {
                        "current_slide_url": image_url,
                        "current_slide_number": str(slide_no),
                        "total_slides": str(total_slides),
                    }
                )
                logger.info(f"📊 Displaying Slide {slide_no}/{total_slides}")
            except Exception as e:
                logger.error(f"❌ Failed to set slide attributes: {e}")
                current_slide_index += 1
                continue

            try:
                # Generate speech for slide
                slide_instruction = (
                    f"Slide {slide_no}: {content_text}\n\n"
                    "Present this slide's key points clearly in 3-4 sentences."
                )

                max_retries = 3
                speech_handle = None
                for attempt in range(max_retries):
                    try:
                        speech_handle = session.generate_reply(
                            instructions=slide_instruction
                        )
                        await speech_handle.wait_for_playout()
                        break
                    except Exception as e:
                        is_last_attempt = attempt == (max_retries - 1)
                        if is_last_attempt:
                            logger.error(
                                f"❌ All {max_retries} attempts failed for Slide {slide_no}."
                            )
                            raise e
                        else:
                            logger.warning(
                                f"⚠️ Attempt {attempt+1} failed (likely cold start). Retrying in 1s..."
                            )
                            await asyncio.sleep(1.0)

                # Check if the presentation was interrupted by the user (e.g., "Stop", "Explain more")
                if speech_handle and speech_handle.interrupted:
                    logger.info(
                        f"⚠️ Slide {slide_no} presentation interrupted. Stopping auto-advance."
                    )
                    break

                logger.info(f"✅ Completed slide {slide_no}.")
                await asyncio.sleep(2.0)

                # Advance to next slide
                current_slide_index += 1

            except Exception as e:
                logger.error(f"❌ Error presenting slide {slide_no}: {e}")
                current_slide_index += 1
                continue

        # 7. Final message
        if current_slide_index >= total_slides:
            try:
                logger.info("🎉 All slides presented.")
                final_speech = session.generate_reply(
                    instructions="Thank you for your attention! I'd be happy to answer questions or navigate to any slide you'd like to review."
                )
                await final_speech.wait_for_playout()
            except Exception as e:
                logger.error(f"❌ Error in final message: {e}")

        logger.info("✅ Presentation complete. Entering interactive Q&A mode.")
        await keep_alive(ctx)

    except asyncio.CancelledError:
        logger.info("🛑 Agent cancelled. Cleaning up...")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        # Cleanup
        logger.info("🧹 Starting cleanup...")

        if session:
            try:
                await session.aclose()
                logger.info("✅ Session closed.")
            except Exception as e:
                logger.error(f"❌ Error closing session: {e}")

        try:
            await ctx.room.disconnect()
            logger.info("✅ Disconnected from room.")
        except Exception as e:
            logger.error(f"❌ Error disconnecting: {e}")

        # Reset global state
        current_slide_index = 0
        total_slides = 0
        slides_data = []
        room_context = None

        logger.info("✅ Cleanup complete.")


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            drain_timeout=1800,  # 30 minutes
        )
    )

# # agent/main.py
# import asyncio
# import logging
# from livekit.agents import (
#     Agent,
#     AgentSession,
#     AutoSubscribe,
#     JobContext,
#     WorkerOptions,
#     cli,
# )
# from livekit.agents.voice import VoiceActivityVideoSampler, room_io
# from llm.gemini import create_llm
# from avatar.anam_avatar import create_avatar
# from avatar.persona import SYSTEM_INSTRUCTIONS
# from utils.safety import keep_alive
# from core.supabase import supabase

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger("dia-presenter-agent")
# logger.setLevel(logging.INFO)


# async def entrypoint(ctx: JobContext):
#     """
#     Core entrypoint for the AI Agent worker.
#     """
#     logger.info(f"🚀 Initializing agent for room: {ctx.room.name}")

#     session = None
#     avatar = None

#     try:
#         # 1. Connect to room
#         await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_ALL)
#         logger.info("✅ Successfully connected to LiveKit room.")

#         # 2. Get presentation ID from participant metadata
#         await asyncio.sleep(2.5)

#         presentation_id = None
#         for participant in ctx.room.remote_participants.values():
#             if participant.metadata:
#                 presentation_id = participant.metadata
#                 logger.info(f"✅ Verified Presentation ID: {presentation_id}")
#                 break

#         if not presentation_id:
#             logger.error("❌ FATAL: No presentation_id found in metadata.")
#             return

#         # 3. Load slides from Supabase
#         logger.info(f"🔍 Querying slides for: {presentation_id}")
#         query_result = (
#             supabase.table("slides")
#             .select("*")
#             .eq("presentation_id", presentation_id)
#             .order("slide_number", desc=False)
#             .execute()
#         )

#         slides = query_result.data
#         if not slides:
#             logger.error(f"❌ No slides found for presentation {presentation_id}")
#             return
#         logger.info(f"✅ Loaded {len(slides)} slides successfully.")

#         # 4. Initialize LLM and Avatar
#         llm = create_llm()
#         logger.info("✅ Gemini LLM initialized.")

#         avatar = create_avatar()
#         logger.info("✅ Anam Avatar initialized.")

#         # 5. Create Agent Session
#         session = AgentSession(
#             llm=llm,
#             video_sampler=VoiceActivityVideoSampler(speaking_fps=0, silent_fps=0),
#             preemptive_generation=False,
#             min_endpointing_delay=2.0,
#             max_endpointing_delay=5.0,
#         )
#         logger.info("✅ Agent session configured.")

#         # Start avatar
#         await avatar.start(session, room=ctx.room)
#         logger.info("✅ Anam avatar started.")

#         # Build instructions
#         presenter_instructions = (
#             f"{SYSTEM_INSTRUCTIONS}\n\n"
#             "ROLE: You are presenting a slide deck to an audience.\n"
#             "GOAL: Present each slide's content clearly and engagingly.\n"
#             "STRICT LIMIT: Maximum 2 sentences per response.\n"
#             "TONE: Professional, clear, and engaging."
#         )

#         # Start session
#         await session.start(
#             agent=Agent(instructions=presenter_instructions),
#             room=ctx.room,
#             room_input_options=room_io.RoomInputOptions(video_enabled=True),
#         )
#         logger.info("✅ Agent session started.")

#         # 6. Present slides
#         logger.info("🎬 Starting presentation sequence.")

#         for idx, slide in enumerate(slides, start=1):
#             slide_no = slide.get("slide_number", idx)
#             image_url = slide.get("image_url", "")
#             content_text = slide.get("extracted_text", "")

#             if not image_url:
#                 logger.warning(f"⚠️ Slide {slide_no} has no image. Skipping.")
#                 continue

#             try:
#                 # FIXED: Set both attributes
#                 await ctx.room.local_participant.set_attributes(
#                     {
#                         "current_slide_url": image_url,
#                         "current_slide_number": str(slide_no),  # Frontend needs this!
#                     }
#                 )
#                 logger.info(f"📊 Displaying Slide {slide_no}/{len(slides)}")
#             except Exception as e:
#                 logger.error(f"❌ Failed to set slide attributes: {e}")
#                 continue

#             try:
#                 # Generate speech
#                 slide_instruction = (
#                     f"Slide {slide_no}: {content_text}\n\n"
#                     "Present this slide's key points clearly in 1-2 sentences."
#                 )

#                 # FIXED: Correct method name
#                 speech_handle = session.generate_reply(instructions=slide_instruction)

#                 # FIXED: Use wait_for_playout() not wait_for_next_playout()
#                 await speech_handle.wait_for_playout()

#                 logger.info(f"✅ Completed slide {slide_no}.")
#                 await asyncio.sleep(2.0)

#             except Exception as e:
#                 logger.error(f"❌ Error presenting slide {slide_no}: {e}")
#                 continue

#         # 7. Final message
#         try:
#             logger.info("🎉 All slides presented.")
#             final_speech = session.generate_reply(
#                 instructions="Thank you for your attention! I'd be happy to answer any questions."
#             )
#             await final_speech.wait_for_playout()  # FIXED: Correct method
#         except Exception as e:
#             logger.error(f"❌ Error in final message: {e}")

#         logger.info("✅ Presentation complete. Entering Q&A mode.")
#         await keep_alive(ctx)

#     except asyncio.CancelledError:
#         logger.info("🛑 Agent cancelled. Cleaning up...")
#     except Exception as e:
#         logger.error(f"❌ Unexpected error: {e}")
#         import traceback

#         traceback.print_exc()
#     finally:
#         # Cleanup
#         logger.info("🧹 Starting cleanup...")

#         if session:
#             try:
#                 await session.aclose()
#                 logger.info("✅ Session closed.")
#             except Exception as e:
#                 logger.error(f"❌ Error closing session: {e}")

#         try:
#             await ctx.room.disconnect()
#             logger.info("✅ Disconnected from room.")
#         except Exception as e:
#             logger.error(f"❌ Error disconnecting: {e}")

#         logger.info("✅ Cleanup complete.")


# if __name__ == "__main__":
#     cli.run_app(
#         WorkerOptions(
#             entrypoint_fnc=entrypoint,
#             drain_timeout=1800,  # 30 minutes
#         )
#     )
