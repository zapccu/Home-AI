import configparser as cp
import speech_recognition as sr
import boto3
import pygame
import threading
import sys
import os
import openai
import wave

def listenForActivationWord(recognizer, microphone, activationWord, listenTime):
    with microphone as source:
        print(f"Listening for {listenTime} seconds ...")
        #audio = recognizer.listen(source, timeout=5)
        audio = recognizer.record(source, duration=int(listenTime))

    try:
        result = recognizer.recognize_google(audio)
        print("Understood " + result)
        words = result.lower().split()
        print(words)

        if activationWord in words:
            print("Activation word detected")
            return True
        else:
            print("List of words does not contain activation word " + activationWord)

    except LookupError:
        print("Could not understand audio")
    except sr.UnknownValueError:
        print("No input or unknown value")
        pass

    return False
                    
def main():
    # Read configuration
    configFile = "homeaidev.conf" if len(sys.argv) < 2 else sys.argv[1]
    config = cp.ConfigParser()
    config['common'] = {
        'keyword': 'computer',
        'duration': 3,
        'audiofiles': os.path.dirname(os.path.realpath(__file__)) + "/audio"
    }

    if not os.path.isfile(configFile):
        print(f"Config file {configFile} not found. Using default values.")
    else:
        config.read(configFile)

    keyword = config['common']['keyword']
    keywordDuration = config['common']['duration']

    # Setup recognizer
    r = sr.Recognizer()
    r.energy_threshold = 100

    m = sr.Microphone()
    # print(sr.Microphone.list_microphone_names())

    listenForActivationWord(r, m, keyword, keywordDuration)

if __name__ == "__main__":
    # startup_sound()
    # startup_sound_state = 0
    main()
