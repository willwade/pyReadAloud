from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()
aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
aws_region = os.getenv('AWS_DEFAULT_REGION')

import boto3
import json

def get_polly_voices():
    # Create a Polly client
    polly_client = boto3.client('polly')

    # Retrieve list of voices
    response = polly_client.describe_voices()

    # List to hold formatted voices
    voices_list = []

    # Process each voice in the response
    for voice in response['Voices']:
        # Extract necessary details and format them
        voice_entry = {
            "name": voice['Id'],
            "country": voice['LanguageName'],
            "languageCodes": [voice['LanguageCode']],
            "ssmlGender": voice['Gender'],
            "naturalSampleRateHertz": voice['SupportedSampleRates'][0]
        }
        voices_list.append(voice_entry)

    # Convert the list to JSON
    with open('polly_voices.json', 'w') as json_file:
        json.dump(voices_list, json_file, indent=2)

    return voices_list

# Execute the function
get_polly_voices()
