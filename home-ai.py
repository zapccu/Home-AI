import configparser as cp
import argparse
import speech_recognition as sr
import boto3
import pyaudio
import pygame
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

# Set default parameters
CONFIG['common'] = {
    'activationWord': 'computer',
    'stopWord': 'beenden',
    'duration': 3,
    'energyThreshold': 100.0,
    'audiofiles': os.path.dirname(os.path.realpath(__file__)) + "/audio"
}
CONFIG['AWS'] = {
    'awsKeyId': 'none',
    'awsKeySecret': 'none',
    'region': 'eu-west-2',
    'pollyVoiceId': 'Daniel',
    'language': 'de-DE'
}
CONFIG['OpenAI'] = {
    'openAIKey': 'none',
    'openAILanguage': 'de',
    'openAIModel': 'gpt-3.5-turbo'
}

# Audio parameters
SAMPLE_RATE      = 16000    # bit/s
READ_CHUNK       = 4096     # Chunk size for output of audio date >4K
CHANNELS         = 1        # Mono
BYTES_PER_SAMPLE = 2        # Bytes per sample

logMessage_LEVEL = 0


# ####################################################
#  Write logMessage messages
# ####################################################

def logMessage(level, message):
    if level >= logMessage_LEVEL:
        print(message)

# ####################################################
#  Read configuration from file
# ####################################################

def readConfig(configFile):
    try:
        if not os.path.isfile(configFile):
            raise FileNotFoundError(f"Config file {configFile} not found.")

        logMessage(1, f"Reading config file {configFile} ...")
        CONFIG.read(configFile)

        # HomeAI won't work without API credentials
        if CONFIG['OpenAI']['openAIKey'] == 'none':
            raise ValueError("Open AI API key not configured")
        if CONFIG['AWS']['awsKeyId'] == 'none':
            raise ValueError("AWS key id not configured")
        if CONFIG['AWS']['awsKeySecret'] == 'none':
            raise ValueError("AWS key not configured")

        openai.api_key = CONFIG['OpenAI']['openAIKey']
        CONFIG['messages']['welcome'].format(activationWord=CONFIG['common']['activationWord'])

        return True
    
    except ValueError as err:
        logMessage(0, err)
    except FileNotFoundError as err:
        logMessage(0, err)

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
            logMessage(2, f"Listening for {listenTime} seconds for activation word {activationWord} ...")
            audio = recognizer.listen(source, timeout=float(listenTime))
            #audio = recognizer.record(source, duration=float(listenTime))

        result = recognizer.recognize_google(audio, language=CONFIG['common']['language'])
        logMessage(2, "Understood " + result)
        words = result.lower().split()
        logMessage(2, words)

        # Next statement will raise a ValueError exception of activation word is not found
        words.index(activationWord)

        return True

    except ValueError:   # Raised by index()
        logMessage(0, "Value Error: List of words does not contain activation word " + activationWord)
    except LookupError:
        logMessage(0, "Lookup Error: Could not understand audio")
    except sr.UnknownValueError:
        logMessage(0, "Unknown Value Error: No input or unknown value")
    except sr.WaitTimeoutError:
        logMessage(0, "Listening timed out")

    return False


# ####################################################
#  Listen for OpenAI command
# ####################################################

def listenForOpenAICommand(recognizer, microphone):
    listenTime = CONFIG['common']['duration']
    recFile = CONFIG['common']['audiofiles'] + "/openairec.wav"

    try:
        # Listen
        with microphone as source:
            logMessage(2, f"Listening for query for {listenTime} seconds ...")
            audio = recognizer.listen(source, timeout=float(listenTime))

        # try recognizing the speech in the recording
        # if the speech is unintelligible, `UnknownValueError` will be thrown
        audioData = audio.get_raw_data()

        # Save the audio as a WAV file
        with wave.open(recFile, "wb") as wavFile:
            wavFile.setnchannels(CHANNELS)  # Mono
            wavFile.setsampwidth(BYTES_PER_SAMPLE)  # 2 bytes per sample
            wavFile.setframerate(audio.sample_rate)  # Use original sample rate
            wavFile.writeframes(audioData)
            wavFile.close()

        audioFile = open(recFile, "rb")
        text = openai.Audio.transcribe("whisper-1", audioFile, language=CONFIG['common']['openAILanguage'])
        audioFile.close()

        logMessage(2, text)
        logMessage(2, text['text'])
        command = text['text']

        if command == "":
            logMessage(2, "Couldn't understand the command")
#            play_audio_file('nicht_verstanden.mp3')
            return None

        return command
    
    except sr.UnknownValueError:
        logMessage(0, "Couldn't understand the command")
 #       play_audio_file('nicht_verstanden.mp3')
    except sr.WaitTimeoutError:
        logMessage(0, "No input")

    return None


# ####################################################
#  Ask Chat GPT
# ####################################################

def askChatGPT(prompt):
    messages = [{"role": "user", "content": prompt}]
    response = openai.ChatCompletion.create(model=CONFIG['OpenAI']['openAIModel'], messages=messages, temperature=0)
    return response.choices[0].message["content"]


# ####################################################
#  Play an audio file
#    loops = -1: play endlessly
# ####################################################

def playAudioFile(fileName, background=False, loops=0):

    if not os.path.isfile(fileName):
        logMessage(2, f"Can't play audio file {fileName}. File not found.")
        return
    
    pygame.mixer.init()
    pygame.mixer.music.load(fileName)
    pygame.mixer.music.play(loops)

    if not background:
        # Wait until the audio playback is complete
        while pygame.mixer.music.get_busy():
            pass


# ####################################################
#  Play an audio PCM stream
# ####################################################

def playAudioStream(stream):
    p = pyaudio.PyAudio()
    stream = p.open(format=p.get_format_from_width(BYTES_PER_SAMPLE),
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        output=True)

    with closing(stream) as pollyStream:
        while True:
            data = pollyStream.read(READ_CHUNK)
            if data is None or len(data) == 0:
                break
            stream.write(data)

    stream.stop_stream()
    stream.close()
    p.terminate()


# ############################################################################
#  Convert text to speech
#    outputFile: Name of temporary audio file relative to configuration
#       parameter audiofiles
# ############################################################################

def textToSpeech(text, outputFile=None):
    session = boto3.Session(
        accessKeyId=CONFIG['AWS']['awsKeyId'],
        secretAccessKey=CONFIG['AWS']['awsKeySecret'],
        regionName='eu-central-1'  # Replace with your desired AWS region
    )
    polly = session.client('polly')

    # Determine audio output format
    if outputFile is None:
        format = "pcm"
    else:
        format = "mp3"
        fileName = CONFIG['common']['audioFiles'] + "/" + outputFile + "." + format

    try:
        # Convert text to stream
        response = polly.synthesize_speech(
            Engine='neural',
            Text=text,
            OutputFormat=format,
            VoiceId=CONFIG['AWS']['pollyVoiceId'],
            LanguageCode=CONFIG['AWS']['language'],
            SampleRate=str(SAMPLE_RATE)
        )

    except (BotoCoreError, ClientError) as error:
        logMessage(0, error)
        return

    # Output stream
    if outputFile is None:
        playAudioStream(response['AudioStream'])
    else:
        if not os.path.isfile(fileName):
            # Write stream to file
            with open(fileName, 'wb') as f:
                f.write(response['AudioStream'].read())
        playAudioFile(fileName)


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
            logMessage(2, "Selected microphone " + name)
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
    parser.add_argument("--log_level", default=0, choices=range(0, 2), help="Set level of log messages")
    parser.add_argument("--version", action="version", version='%(prog)s ' + VERSION)
    args = parser.parse_args()

    # List available microphones
    if args.list_microphones:
        listMicrophones()
        return

    LOG_LEVEL = args.log_level

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

    # Output welcome message
    textToSpeech(CONFIG['messages']['welcome'], "welcome.mp3")

    while True:
        if listenForActivationWord(recognizer, microphone):
            playAudioFile("listening.wav")
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
