from dotenv import load_dotenv
import os
import boto3
import json
from google.cloud import texttospeech as google_tts
from ibm_watson import TextToSpeechV1
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
import azure.cognitiveservices.speech as speechsdk

# Load environment variables
load_dotenv()

# Helper functions for each service
def get_google_voices():
    try:
        client = google_tts.TextToSpeechClient()
        response = client.list_voices()
        return [{"name": voice.name, "country": voice.language_codes[0]} for voice in response.voices]
    except Exception as e:
        print(f"Error fetching Google voices: {e}")

def get_aws_voices():
    try:
        polly_client = boto3.client('polly')
        response = polly_client.describe_voices()
        return [{"name": voice['Id'], "country": voice['LanguageName']} for voice in response['Voices']]
    except Exception as e:
        print(f"Error fetching AWS voices: {e}")

def get_ibm_voices():
    try:
        api_key = os.getenv('IBM_API_KEY')
        url = os.getenv('IBM_URL')
        authenticator = IAMAuthenticator(api_key)
        text_to_speech = TextToSpeechV1(authenticator=authenticator)
        text_to_speech.set_service_url(url)
        voices = text_to_speech.list_voices().get_result()
        return [{"name": voice['name'], "country": voice['language']} for voice in voices['voices']]
    except Exception as e:
        print(f"Error fetching IBM voices: {e}")

def get_azure_voices():
    try:
        key = os.getenv('AZURE_SUBSCRIPTION_KEY')
        region = os.getenv('AZURE_REGION')
        
        if not key or not region:
            print("Azure credentials are missing!")
            return None
        
        speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)
        result = synthesizer.get_voices_async().get()

        if result.voices:
            voices = [{"name": voice.short_name, "country": voice.locale} for voice in result.voices]
            print(f"Retrieved {len(voices)} voices from Azure.")
            return voices
        else:
            print("No voices returned from Azure. Check the API key and region.")
            return None

    except Exception as e:
        print(f"Error fetching Azure voices: {e}")
        return None


# Main function to call APIs
def update_tts_voices(platforms):
    results = {}
    if 'google' in platforms:
        results['google'] = get_google_voices()
    if 'aws' in platforms:
        results['aws'] = get_aws_voices()
    if 'ibm' in platforms:
        results['ibm'] = get_ibm_voices()
    if 'azure' in platforms:
        results['azure'] = get_azure_voices()

    # Save results to JSON files
    for platform, voices in results.items():
        if voices:
            with open(f'{platform}_voices.json', 'w') as f:
                json.dump(voices, f, indent=2)


# Example usage
platforms = input("Enter the platforms to update (google, aws, ibm, azure): ").split()
update_tts_voices(platforms)
