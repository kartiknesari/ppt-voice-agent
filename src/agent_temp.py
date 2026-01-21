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


# ==================== HELPER FUNCTIONS ====================


def get_slide_context(current_idx, slides, window=1):
    """
    Get current slide with FULL content plus brief context from nearby slides.
    This ensures current slide is fully explained while keeping context manageable.
    """
    start = max(0, current_idx - window)
    end = min(len(slides), current_idx + window + 1)

    context = ""

    # Add previous slides with limited content
    for i in range(start, current_idx):
        text = slides[i].get("extracted_text", "")[:100]
        context += f"Previous Slide {i+1}: {text}...\n\n"

    # Add CURRENT slide with FULL content
    current_slide_text = slides[current_idx].get(
        "extracted_text", "No content available"
    )
    context += f"===== CURRENT SLIDE {current_idx+1} (PRESENT THIS) =====\n{current_slide_text}\n\n"

    # Add next slides with limited content
    for i in range(current_idx + 1, end):
        text = slides[i].get("extracted_text", "")[:100]
        context += f"Next Slide {i+1}: {text}...\n"

    return context


# ==================== NAVIGATION TOOL FUNCTIONS ====================


@function_tool(description="Move to the next slide in the presentation")
async def next_slide():
    """Move to the next slide when user says 'next', 'next slide', or 'move forward'"""
    global current_slide_index, total_slides

    if current_slide_index < total_slides - 1:
        current_slide_index += 1
        await update_slide_display()

        # Get new slide content (shortened for speed)
        slide = slides_data[current_slide_index]
        content = slide.get("extracted_text", "")[:80]

        logger.info(f"✅ Moved to slide {current_slide_index + 1}")
        return f"Slide {current_slide_index + 1}/{total_slides}"
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

        # Get new slide content (shortened for speed)
        slide = slides_data[current_slide_index]
        content = slide.get("extracted_text", "")[:80]

        logger.info(f"✅ Moved to slide {current_slide_index + 1}")
        return f"Slide {current_slide_index + 1}/{total_slides}"
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

        # Get new slide content (shortened for speed)
        slide = slides_data[current_slide_index]
        content = slide.get("extracted_text", "")[:80]

        logger.info(f"✅ Jumped to slide {slide_number}")
        return f"Slide {slide_number}/{total_slides}"
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

        # DEBUGGING: Log content availability for all slides
        slides_with_content = 0
        slides_without_content = []
        for idx, slide in enumerate(slides_data):
            content = slide.get("extracted_text", "")
            if content and content.strip():
                slides_with_content += 1
            else:
                slides_without_content.append(idx + 1)

        logger.info(f"📊 Slides with content: {slides_with_content}/{total_slides}")
        if slides_without_content:
            logger.warning(f"⚠️ Slides WITHOUT content: {slides_without_content}")
        else:
            logger.info("✅ All slides have extracted text content")

        # 4. Initialize LLM and Avatar
        llm = create_llm()
        logger.info("✅ Gemini LLM initialized.")

        avatar = create_avatar()
        logger.info("✅ Anam Avatar initialized.")

        # 5. Create Agent Session with OPTIMIZED settings
        session = AgentSession(
            llm=llm,
            video_sampler=VoiceActivityVideoSampler(speaking_fps=0, silent_fps=0),
            preemptive_generation=False,
            min_endpointing_delay=1.5,  # Reduced from 2.0 for faster responses
            max_endpointing_delay=4.0,  # Reduced from 5.0
        )
        logger.info("✅ Agent session configured.")

        # Start avatar
        await avatar.start(session, room=ctx.room)
        logger.info("✅ Anam avatar started.")

        # DIAGNOSTIC: Log system instructions to check for language conflicts
        logger.info(f"📋 System instructions preview: {SYSTEM_INSTRUCTIONS[:200]}...")
        if "chinese" in SYSTEM_INSTRUCTIONS.lower() or "中文" in SYSTEM_INSTRUCTIONS:
            logger.warning(
                "⚠️ WARNING: SYSTEM_INSTRUCTIONS may contain Chinese language directives!"
            )

        # CRITICAL: Don't send ALL slides upfront - this causes timeouts
        # Only send a brief overview
        presentation_overview = (
            f"You are presenting a {total_slides}-slide presentation. "
            "Context for each slide will be provided when needed. "
            "Listen for navigation commands."
        )

        # Build SHORT instructions to reduce initial processing time
        # IMPORTANT: Place language requirement FIRST to override any conflicting system instructions
        presenter_instructions = (
            "# CRITICAL LANGUAGE REQUIREMENT\n"
            "YOU MUST ALWAYS SPEAK IN ENGLISH ONLY. NEVER USE CHINESE, SPANISH, OR ANY OTHER LANGUAGE.\n"
            "IF YOU DETECT YOURSELF SPEAKING IN ANOTHER LANGUAGE, IMMEDIATELY STOP AND SWITCH TO ENGLISH.\n\n"
            f"{SYSTEM_INSTRUCTIONS}\n\n"
            "# PRESENTATION CONTEXT\n"
            f"This is a {total_slides}-slide presentation. "
            "You will receive specific slide content for each slide.\n\n"
            "# STRICT BEHAVIORAL RULES\n"
            "1. LANGUAGE: English only - no exceptions\n"
            "2. SCOPE: Only discuss content from the current slide provided\n"
            "3. ACCURACY: Never make up information not in the slide\n"
            "4. FOCUS: Never discuss topics outside this specific presentation\n"
            "5. BREVITY: Keep responses to 3-4 sentences maximum\n"
            "6. TONE: Professional, clear, and engaging\n\n"
            "# NAVIGATION TOOLS\n"
            "You can control slides using:\n"
            "- next_slide(): Move to next slide\n"
            "- previous_slide(): Move to previous slide\n"
            "- goto_slide(N): Jump to slide N\n"
            "Listen for commands like 'next', 'previous', 'go to slide 3'."
        )

        # Start session with tools
        await session.start(
            agent=Agent(
                instructions=presenter_instructions,
                tools=[next_slide, previous_slide, goto_slide],
            ),
            room=ctx.room,
            room_input_options=room_io.RoomInputOptions(video_enabled=True),
        )
        logger.info("✅ Agent session started with navigation tools.")

        # 6. Present slides automatically
        logger.info("🎬 Starting presentation sequence.")

        # IMPORTANT: Longer warmup to let LLM initialize properly (prevents first-slide timeout)
        await asyncio.sleep(5.0)

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
                # OPTIMIZED: Use contextual slides instead of full presentation
                slide_context = get_slide_context(
                    current_slide_index, slides_data, window=1
                )

                # CRITICAL: Verify we have content to present
                if not content_text or content_text.strip() == "":
                    logger.warning(
                        f"⚠️ Slide {slide_no} has no extracted text content. Using placeholder."
                    )
                    content_text = f"Slide {slide_no} content"

                # Log what we're sending to LLM for debugging
                logger.info(
                    f"📝 Slide {slide_no} content length: {len(content_text)} chars"
                )
                logger.debug(f"Content preview: {content_text[:100]}...")

                # Generate speech for slide with FULL current slide content
                slide_instruction = (
                    f"{slide_context}\n\n"
                    "===== YOUR TASK =====\n"
                    "1. Present ONLY the content from the CURRENT SLIDE marked above\n"
                    "2. Speak ONLY in English - no other languages allowed\n"
                    "3. Cover the key points in 3-4 sentences\n"
                    "4. Do NOT add information not present in the slide\n"
                    "5. Do NOT discuss unrelated topics\n"
                    "6. Stay focused on THIS presentation"
                )

                # IMPROVED retry mechanism with timeout
                max_retries = 2  # Reduced from 3 to fail faster
                speech_handle = None
                success = False

                for attempt in range(max_retries):
                    try:
                        logger.info(f"🎤 Attempt {attempt+1} for slide {slide_no}")

                        # CRITICAL: Reset instruction context each attempt to prevent drift
                        fresh_slide_instruction = (
                            f"{slide_context}\n\n"
                            "===== YOUR TASK =====\n"
                            "1. Present ONLY the content from the CURRENT SLIDE marked above\n"
                            "2. Speak ONLY in English - no other languages allowed\n"
                            "3. Cover the key points in 3-4 sentences\n"
                            "4. Do NOT add information not present in the slide\n"
                            "5. Do NOT discuss unrelated topics\n"
                            "6. Stay focused on THIS presentation"
                        )

                        speech_handle = session.generate_reply(
                            instructions=fresh_slide_instruction
                        )

                        # Add explicit timeout to prevent indefinite hangs
                        await asyncio.wait_for(
                            speech_handle.wait_for_playout(),
                            timeout=25.0,  # 25 second timeout
                        )

                        success = True
                        logger.info(f"✅ Completed slide {slide_no}")
                        break  # Exit retry loop on success

                    except asyncio.TimeoutError:
                        logger.warning(
                            f"⏱️ Timeout on attempt {attempt+1} for slide {slide_no}"
                        )
                        if attempt < max_retries - 1:
                            logger.info(f"Retrying in 1.5 seconds...")
                            await asyncio.sleep(1.5)  # Shorter retry delay
                        else:
                            logger.error(
                                f"❌ All {max_retries} attempts timed out for slide {slide_no}"
                            )

                    except Exception as e:
                        logger.warning(f"⚠️ Attempt {attempt+1} failed: {str(e)[:100]}")
                        if attempt < max_retries - 1:
                            logger.info(f"Retrying in 1.5 seconds...")
                            await asyncio.sleep(1.5)
                        else:
                            logger.error(
                                f"❌ All {max_retries} attempts failed for slide {slide_no}"
                            )

                # Check if the presentation was interrupted by the user
                if (
                    speech_handle
                    and hasattr(speech_handle, "interrupted")
                    and speech_handle.interrupted
                ):
                    logger.info(
                        f"⚠️ Slide {slide_no} presentation interrupted. Stopping auto-advance."
                    )
                    break

                if success:
                    await asyncio.sleep(1.5)  # Shorter pause between slides
                    current_slide_index += 1
                else:
                    # Skip failed slide and continue
                    logger.warning(f"⚠️ Skipping slide {slide_no} due to errors")
                    current_slide_index += 1

            except Exception as e:
                logger.error(f"❌ Unexpected error presenting slide {slide_no}: {e}")
                current_slide_index += 1
                continue

        # 7. Final message
        if current_slide_index >= total_slides:
            try:
                logger.info("🎉 All slides presented.")
                final_speech = session.generate_reply(
                    instructions="Thank you for your attention! I'd be happy to answer questions or navigate to any slide you'd like to review."
                )

                # Add timeout to final message too
                await asyncio.wait_for(final_speech.wait_for_playout(), timeout=15.0)
            except asyncio.TimeoutError:
                logger.warning("⏱️ Final message timed out")
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
