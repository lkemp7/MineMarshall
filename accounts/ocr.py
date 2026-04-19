import json
from datetime import datetime

import easyocr
import ollama
from django.conf import settings


def extract_licence_fields(image_bytes: bytes) -> dict:
    """
    Extract key fields from an Australian driver's licence image.

    Uses easyOCR to pull raw text, then an Ollama LLM to parse it into
    structured JSON matching the patterns found in the working OCR-dev experiment.

    Returns a dict with keys: first_name, last_name, dob (YYYY-MM-DD), licence_number, expiry.
    Any field that cannot be extracted is None.
    """
    empty = {"title": None, "first_name": None, "last_name": None, "dob": None, "licence_number": None, "expiry": None}
    try:
        reader = easyocr.Reader(["en"], verbose=False)
        results = reader.readtext(image_bytes, detail=0)
        raw_text = " ".join(results)
    except Exception:
        return empty

    if not raw_text.strip():
        return empty
    try:
        response = ollama.chat(
            model='llama3.2:3b',
            messages=[
                {
                'role': 'system',
                'content': 'You are a data extraction assistant. You only output raw JSON for later parsing by the user. Under no circumstances will you use markdown or code snippets. Do not explain your responses. All responses must start with a { and end with a }.'  
                },
                {
                'role': 'user',
                'content': f'''Extract the following fields from this driver licence OCR text. 
                Return JSON with keys: surname, given_names, licence_number, dob, expiry.
                If a field is not found, use null. 
                The licence number will contain 9 characters, and only contain digits 0-9.  
                Return DOB in the format DD/MM/YYYY.
                The licence contains an "effective" date and an "expiry" date - ensure that only the expiry date is extracted. This will be the later of the two dates. Return expiry in the formar DD/MM/YY.
                OCR text: {raw_text}'''
            }]
        )
        data = json.loads(response["message"]["content"])
    except (json.JSONDecodeError, Exception):
        return empty

    dob_raw = data.get("dob")
    dob_formatted = None
    if dob_raw:
        try:
            dob_formatted = datetime.strptime(dob_raw, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    expiry_raw = data.get("expiry")
    expiry_formatted = None
    if expiry_raw:
        for x in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                expiry_formatted = datetime.strptime(expiry_raw, x).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue

    return {
        "title": "Driver Licence",
        "first_name": data.get("given_names") or None,
        "last_name": data.get("surname") or None,
        "dob": dob_formatted,
        "licence_number": data.get("licence_number") or None,
        "expiry": expiry_formatted
    }
