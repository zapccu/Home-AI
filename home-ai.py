import configparser as cp
import argparse
import speech_recognition as sr
import boto3
import pyaudio
# import pygame
import threading
import sys
import os
import time
import openai
import wave
from contextlib import closing
from botocore.exceptions import BotoCoreError, ClientError

VERSION = "1.0.0"

# Configuration
CONFIG = cp.ConfigParser()

# Audio parameters
SAMPLE_RATE      = 16000    # bit/s
READ_CHUNK       = 4096     # Chunk size for output of audio date >4K
CHANNELS         = 1        # Mono
BYTES_PER_SAMPLE = 2        # Bytes per sample


# ####################################################
#  Read configuration from file
# ####################################################

def readConfig(configFile):
    # Set default parameters
    CONFIG['common'] = {
        'activationWord': 'computer',
        'stopWord': 'beenden',
        'duration': 3,
        'energyThreshold': 100.0,
        'pollyVoiceId': 'Daniel',
        'language': 'de-DE',
        'openAILanguage': 'de',
        'openAIModel': 'gpt-3.5-turbo',
        'audiofiles': os.path.dirname(os.path.realpath(__file__)) + "/audio"
    }
    CONFIG['API'] = {
        'openAIKey': 'none',
        'awsKeyId': 'none',
        'awsKeySecret': 'none'
    }

    try:
        if not os.path.isfile(configFile):
            raise FileNotFoundError(f"Config file {configFile} not found.")

        print(f"Reading config file {configFile} ...")
        CONFIG.read(configFile)

        # HomeAI won't work without API credentials
        if CONFIG['API']['openAIKey'] == 'none':
            raise ValueError("Open AI API key not configured")
        if CONFIG['API']['awsKeyId'] == 'none':
            raise ValueError("AWS key id not configured")
        if CONFIG['API']['awsKeySecret'] == 'none':
            raise ValueError("AWS key not configured")

        openai.api_key = CONFIG['API']['openAIKey']

        return True
    
    except ValueError as err:
        print(err)
    except FileNotFoundError as err:
        print(err)

    return False    

# ####################################################
#  Listen for activation word
# ####################################################

def listenForActivationWord(recognizer, microphone):

    activationWord = CONFIG['common']['activationWord'].lower()
    listenTime = CONFIG['common']['duration']

    # Listen
    try:
        with microphone as source:
            print(f"Listening for {listenTime} seconds for activation word {activationWord} ...")
            audio = recognizer.listen(source, timeout=float(listenTime))
            #audio = recognizer.record(source, duration=float(listenTime))

        result = recognizer.recognize_google(audio, language=CONFIG['common']['language'])
        print("Understood " + result)
        words = result.lower().split()
        print(words)

        # Next statement will raise a ValueError exception of activation word is not found
        words.index(activationWord)

        return True

    except ValueError:   # Raised by index()
        print("Value Error: List of words does not contain activation word " + activationWord)
    except LookupError:
        print("Lookup Error: Could not understand audio")
    except sr.UnknownValueError:
        print("Unknown Value Error: No input or unknown value")
    except sr.WaitTimeoutError:
        print("Listening timed out")

    return False


# ####################################################
#  Listen for OpenAI command
# ####################################################

def listenForOpenAICommand(recognizer, microphone):
    listenTime = CONFIG['common']['duration']

    try:
        # Listen
        with microphone as source:
            print(f"Listening for query for {listenTime} seconds ...")
            audio = recognizer.listen(source, timeout=float(listenTime))

        # try recognizing the speech in the recording
        # if the speech is unintelligible, `UnknownValueError` will be thrown
        audioData = audio.get_raw_data()

        # Save the audio as a WAV file
        with wave.open("temp_rec.wav", "wb") as wavFile:
            wavFile.setnchannels(CHANNELS)  # Mono
            wavFile.setsampwidth(BYTES_PER_SAMPLE)  # 2 bytes per sample
            wavFile.setframerate(audio.sample_rate)  # Use original sample rate
            wavFile.writeframes(audioData)
            wavFile.close()

        audioFile = open("temp_rec.wav", "rb")
        text = openai.Audio.transcribe("whisper-1", audioFile, language=CONFIG['common']['openAILanguage'])
        audioFile.close()

        print(text)
        print(text['text'])
        command = text['text']

        if command == "":
            print("Couldn't understand the command")
#            play_audio_file('nicht_verstanden.mp3')
            return None

        return command
    
    except sr.UnknownValueError:
        print("Couldn't understand the command")
 #       play_audio_file('nicht_verstanden.mp3')
    except sr.WaitTimeoutError:
        print("No input")

    return None


# ####################################################
#  Convert text to speech
# ####################################################

def textToSpeech(text):
    session = boto3.Session(
        aws_access_key_id=CONFIG['API']['awsKeyId'],
        aws_secret_access_key=CONFIG['API']['awsKeySecret'],
        region_name='eu-central-1'  # Replace with your desired AWS region
    )
    polly = session.client('polly')

    try:
        # Convert text to PCM stream
        response = polly.synthesize_speech(
            Engine='neural',
            Text=text,
            OutputFormat='pcm',
            VoiceId=CONFIG['common']['pollyVoiceId'],
            LanguageCode=CONFIG['common']['language'],
            SampleRate=str(SAMPLE_RATE)
        )

    except (BotoCoreError, ClientError) as error:
        print(error)
        sys.exit(-1)

    # Output stream
    p = pyaudio.PyAudio()
    stream = p.open(format=p.get_format_from_width(BYTES_PER_SAMPLE),
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        output=True)

    with closing(response["AudioStream"]) as polly_stream:
        while True:
            data = polly_stream.read(READ_CHUNK)
            if data is None or len(data) == 0:
                break
            stream.write(data)

    stream.stop_stream()
    stream.close()

    p.terminate()


# ####################################################
#  Ask Chat GPT
# ####################################################

def askChatGPT(prompt):
    messages = [{"role": "user", "content": prompt}]
    response = openai.ChatCompletion.create(model=CONFIG['common']['openAIModel'], messages=messages, temperature=0)
    return response.choices[0].message["content"]


# ####################################################
#  List configured microphones
# ####################################################

def listMicrophones():
    print("Available microphone devices are:")
    for index, name in enumerate(sr.Microphone.list_microphone_names()):
        print(f"Microphone with name \"{name}\" found")


# ####################################################
#  Select microphone
# ####################################################

def selectMicrophone(micName):
    deviceIndex = None
    for index, name in enumerate(sr.Microphone.list_microphone_names()):
        if micName in name:
            deviceIndex = index
            print("Selected microphone " + name)
            break
    return deviceIndex


# ####################################################
#  Main function
# ####################################################

def main():

    # Parse command line arguments
    parser = argparse.ArgumentParser(prog="HomeAI", description="Home AI Assistant")
    parser.add_argument("--config", default="homeai.conf", help="Name of configuration file")
    parser.add_argument("--list_microphones", action="store_true", help="List available microphones")
    parser.add_argument("--microphone", default="default", help="Set name of microphone")
    parser.add_argument("--version", action="version", version='%(prog)s ' + VERSION)
    args = parser.parse_args()

    # List available microphones
    if args.list_microphones:
        listMicrophones()
        return

    # Read configuration
    if not readConfig(args.config):
        return

    # Setup microphone
    deviceIndex = selectMicrophone(args.microphone)
    # microphone = sr.Microphone(sample_rate=SAMPLE_RATE, device_index=deviceIndex)
    microphone = sr.Microphone(sample_rate=SAMPLE_RATE)

    # Setup recognizer
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = False
    if int(CONFIG['common']['energyThreshold']) == -1:
        print("Calibrating energy threshold ...")
        with microphone as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
        print("Speech recognition energy threshold = " + str(recognizer.energy_threshold))
    else:
        recognizer.energy_threshold = CONFIG['common']['energyThreshold']

    textToSpeech("Bitte einen Befehl eingeben")

    while True:
        if listenForActivationWord(recognizer, microphone):
            print(">>> Ask Open AI")

            while True:
                prompt = listenForOpenAICommand(recognizer, microphone)

                if prompt:
                    if prompt == CONFIG['common']['stopWord']:
                        print("Shutting down Home AI")
                        sys.exit()
                    else:
                        response = askChatGPT(prompt)
                        print(response)
                    break

if __name__ == "__main__":
    main()
