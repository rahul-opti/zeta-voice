#!/usr/bin/env python3

import asyncio

import click
import pandas as pd
from tqdm import tqdm

from zeta_voice.tts.tts import TTSService, create_tts_service


async def process_responses_async(
    tts_service: TTSService,
    chatbot_responses: pd.DataFrame,
    intent_response_column: str,
    intent_name_column: str,
    remove_silence: bool,
    max_concurrent: int = 30,
) -> None:
    """Process all responses asynchronously with limited concurrency."""
    # Limit added because ElevenLabs API has a rate limit of 30 concurrent requests.
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_single_response(row: pd.Series) -> None:
        async with semaphore:
            return await tts_service.generate_and_save_recording(
                row[intent_response_column],
                row[intent_name_column],
                intent_response_column,
                remove_silence,
            )

    tasks = []
    for _, row in chatbot_responses.iterrows():
        if not pd.isna(row[intent_response_column]):
            task = process_single_response(row)
            tasks.append(task)

    await asyncio.gather(*tasks)


@click.command()
@click.argument("responses-file-path", required=True)
@click.argument("intent-name-column", required=True)
@click.argument("intent-response-columns", required=True)
@click.argument("voice-name", required=True)
@click.option(
    "--remove-silence/--no-remove-silence",
    default=True,
    help="Whether to remove silence from audio recordings. Defaults to True.",
)
@click.option(
    "--max-concurrent",
    default=5,
    help="Maximum number of concurrent requests to TTS API (ElevenLabs free/creator tiers max at 10-15). Defaults to 5.",
)
@click.option(
    "--skip-fillers",
    is_flag=True,
    default=False,
    help="Skip generation of filler_word_* columns.",
)
@click.option(
    "--only-fillers",
    is_flag=True,
    default=False,
    help="Generate only filler_word_* columns.",
)
def save_chatbot_response_recordings(
    responses_file_path: str,
    intent_name_column: str,
    intent_response_columns: str,
    voice_name: str,
    remove_silence: bool,
    max_concurrent: int,
    skip_fillers: bool,
    only_fillers: bool,
) -> None:
    """Generates speech recordings from chatbot responses in a CSV file."""
    intent_response_columns_list = intent_response_columns.split(",")

    if only_fillers:
        intent_response_columns_list = [c for c in intent_response_columns_list if c.startswith("filler_word_")]
    elif skip_fillers:
        intent_response_columns_list = [c for c in intent_response_columns_list if not c.startswith("filler_word_")]

    if not intent_response_columns_list:
        return None

    chatbot_responses = pd.read_csv(responses_file_path)

    tts_service = create_tts_service(voice_name)

    async def main() -> None:
        try:
            for intent_response_column in tqdm(intent_response_columns_list):
                await process_responses_async(
                    tts_service,
                    chatbot_responses,
                    intent_response_column,
                    intent_name_column,
                    remove_silence,
                    max_concurrent,
                )
        finally:
            await tts_service.cleanup()

    asyncio.run(main())

    click.echo("Text-to-speech generation completed.")


if __name__ == "__main__":
    save_chatbot_response_recordings()
