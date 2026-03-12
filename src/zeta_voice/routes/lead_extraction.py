import base64
import json
from typing import Any
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends
from loguru import logger
from openai import AsyncOpenAI
from zeta_voice.auth import admin_api_key_auth

router = APIRouter()
client = AsyncOpenAI() # Assumes OPENAI_API_KEY is in environment

@router.post("/extract_leads")
async def extract_leads(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image type.")

    try:
        content = await file.read()
        base64_image = base64.b64encode(content).decode("utf-8")
        
        prompt = """
        You are an AI assistant that extracts contact leads from images of handwritten notes, forms, or documents.
        Extract any names and phone numbers you can find in the image.
        Return the result EXACTLY as a JSON array of objects, where each object has "name" and "phone" keys. 
        If a name is not found but a phone number is, leave "name" as an empty string.
        Format the phone number in E.164 format (e.g., "+12345678901"). Do not use spaces or dashes.
        If no country code is present, assume it is a US number and prepend "+1". If a country code is present, keep it and format accordingly with a leading "+".
        Example Output:
        [
            {"name": "John Doe", "phone": "+12345678901"},
            {"name": "Alice Smith", "phone": "+447911123456"}
        ]
        If no leads are found, return an empty array [].
        ONLY return valid JSON. Do not include markdown blocks or any other text.
        """

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{file.content_type};base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500,
        )

        content_str = response.choices[0].message.content or "[]"
        content_str = content_str.strip()
        
        if content_str.startswith("```json"):
            content_str = content_str[7:]
        if content_str.endswith("```"):
            content_str = content_str[:-3]
            
        content_str = content_str.strip()

        try:
            leads = json.loads(content_str)
            if not isinstance(leads, list):
                logger.warning(f"Extracted leads is not a list: {leads}")
                leads = []
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON from AI: {content_str}")
            leads = []

        return {"leads": leads}
    except Exception as e:
        logger.error(f"Error during lead extraction: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process image.")
