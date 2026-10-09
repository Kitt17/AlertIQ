import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY is not set in .env")

client = genai.Client(api_key=API_KEY)


def analyze_email(subject, sender, body):
    prompt = f"""
You are an AI operations assistant for a company.

Analyze the following email and determine whether the operator needs
to take action or follow up.

Email:
Subject: {subject}
Sender: {sender}
Body:
{body}

Return ONLY valid JSON in this exact format:

{{
    "follow_up_required": true,
    "priority": "High",
    "client": "Client name",
    "action_required": "What the operator needs to do",
    "deadline": "YYYY-MM-DD or null",
    "summary": "Short summary of the email"
}}

Rules:
- follow_up_required must be true or false.
- priority must be High, Medium, or Low.
- If there is no clear deadline, use null.
- Do not invent information that is not in the email.
- Keep the summary short.
"""
    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt
        )

        return response.text

    except Exception as e:
        print(f"Gemini AI error: {e}")
        return None


if __name__ == "__main__":
    result = analyze_email(
        "Quotation Request",
        "client@example.com",
        "Hi, could you please send us the quotation for the security service? "
        "We would appreciate receiving it by 2 October 2026."
    )

    print(result)
