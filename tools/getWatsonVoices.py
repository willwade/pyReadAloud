from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()
ibm_api_key = os.getenv('IBM_API_KEY')
ibm_url = os.getenv('IBM_URL')

from ibm_watson import TextToSpeechV1
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
import json

def get_watson_voices(api_key, url):
    # Authenticate to IBM Watson Text to Speech
    authenticator = IAMAuthenticator(api_key)
    text_to_speech = TextToSpeechV1(authenticator=authenticator)
    text_to_speech.set_service_url(url)

    # Retrieve the list of voices
    voices = text_to_speech.list_voices().get_result()

    # List to store formatted voices
    voices_list = []

    # Process each voice
    for voice in voices['voices']:
        # Format each voice entry
        voice_entry = {
            "name": voice['name'],
            "country": voice.get('language', 'Not specified'), # Using get in case some fields are missing
            "languageCodes": [voice['language']],
            "ssmlGender": voice.get('gender', 'Unknown'),
            "naturalSampleRateHertz": voice.get('sample_rate', 'Unknown')
        }
        voices_list.append(voice_entry)

    # Convert the list to JSON and save it to a file
    with open('watson_voices.json', 'w') as json_file:
        json.dump(voices_list, json_file, indent=2)

    return voices_list

# Replace 'your_api_key' and 'your_service_url' with your IBM Watson credentials
get_watson_voices(ibm_api_key, ibm_url)
