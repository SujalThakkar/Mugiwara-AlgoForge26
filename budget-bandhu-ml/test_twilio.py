import dotenv
import os
from twilio.rest import Client

dotenv.load_dotenv()

sid = os.getenv("TWILIO_ACCOUNT_SID")
token = os.getenv("TWILIO_AUTH_TOKEN")
number = os.getenv("TWILIO_PHONE_NUMBER")

print(f"SID: {sid}")
print(f"Token: {'Set' if token else 'Not Set'}")
print(f"Number: {number}")

if sid and token:
    try:
        client = Client(sid, token)
        print("Twilio Client Initialized successfully")
    except Exception as e:
        print(f"Twilio Init Failed: {e}")
else:
    print("Twilio Credentials missing in .env")
