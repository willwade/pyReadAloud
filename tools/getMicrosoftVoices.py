from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()
azure_subscription_key = os.getenv('AZURE_SUBSCRIPTION_KEY')
azure_region = os.getenv('AZURE_REGION')

# You can now use these variables in your API setup

import azure.cognitiveservices.speech as speechsdk
import json

def get_azure_voices(subscription_key, region):
    # Set up the speech configuration with your subscription key and region
    speech_config = speechsdk.SpeechConfig(subscription=subscription_key, region=region)

    # Initialize the speech synthesizer
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)

    # Fetch the list of available voices
    result = synthesizer.get_voices_async().get()

    # List to hold formatted voices
    voices_list = []

    # Parse and format the voices data
    for voice in result.voices:
        voice_entry = {
            "name": voice.short_name,
            "country": voice.locale.split("-")[1] if "-" in voice.locale else voice.locale,
            "languageCodes": [voice.locale],
            "ssmlGender": voice.gender,
            "naturalSampleRateHertz": voice.sample_rate_hertz
        }
        voices_list.append(voice_entry)

    # Save the result to a JSON file
    with open('azure_voices.json', 'w') as json_file:
        json.dump(voices_list, json_file, indent=2)

    return voices_list

# Replace 'your_subscription_key' and 'your_region' with your Azure credentials
get_azure_voices(azure_subscription_key, azure_region)
