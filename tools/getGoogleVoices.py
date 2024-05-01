from dotenv import load_dotenv
import os
import json
from google.cloud import texttospeech

# Load environment variables from .env file
load_dotenv()
google_credentials = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

def list_google_tts_voices():
    try:
        # Create a client
        client = texttospeech.TextToSpeechClient()

        # Perform the API request
        response = client.list_voices()

        # List to store formatted voices
        voices_list = []

        # Parse and format the voices data
        for voice in response.voices:
            voice_entry = {
                "name": voice.name,
                "country": voice.language_codes[0].split('-')[1] if '-' in voice.language_codes[0] else "Global",
                "languageCodes": voice.language_codes,
                "ssmlGender": texttospeech.SsmlVoiceGender(voice.ssml_gender).name,
                "naturalSampleRateHertz": voice.natural_sample_rate_hertz
            }
            voices_list.append(voice_entry)

        # Save the data to a JSON file
        with open('google_voices.json', 'w') as json_file:
            json.dump(voices_list, json_file, indent=2)

        return voices_list
    except Exception as e:
        print("An error occurred:", e)

# Call the function to list voices and save to a JSON file
list_google_tts_voices()
