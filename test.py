import configparser as cp
import speech_recognition as sr
import boto3
import pygame
import threading
import os
import openai
import wave

def listenForActivationWord(recognizer, microphone, activationWord, listenTime):
    with microphone as source:
        print("Listening for " + listenTime + " seconds ...")
        #audio = recognizer.listen(source, timeout=5)
        audio = recognizer.record(source, duration=listenTime)

    try:
        result = recognizer.recognize_google(audio)
        print("Understood " + result)
        words = result.lower().split()
        print(words)

        if activationWord in words:
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
    config = cp.ConfigParser()
    config['common'] = {
        'keyword': 'computer',
        'duration': 3
    }
    config.read("homeai.conf")

    keyword = config['common']['keyword']
    keywordDuration = config['common']['duration']

    # setup recognizer
    r = sr.Recognizer()
    r.energy_threshold = 100

    m = sr.Microphone()
    # print(sr.Microphone.list_microphone_names())

    listenForActivationWord(r, m, keyword, keywordDuration)

if __name__ == "__main__":
    # startup_sound()
    # startup_sound_state = 0
    main()
