import speech_recognition as sr
import boto3
import pygame
import threading
import os
import openai
import wave

###### API KEYS #####
openai.api_key = 'xx'
aws_access_key_id = 'yy'
aws_access_key_secret = 'zz'
###### ------ #####

ACTIVATION_WORD = "computer"  # replace with your activation word or phrase

###### ------ #####

startup_sound_state = 1

def convert_text_to_speech(text, voice_id='Daniel', language_code='de-DE'):
    polly_client = boto3.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_access_key_secret,
        region_name='eu-central-1'  # Replace with your desired AWS region
    ).client('polly')

    response = polly_client.synthesize_speech(
        Engine='neural',
        Text=text,
        OutputFormat='mp3',
        VoiceId=voice_id,
        LanguageCode=language_code
    )

    with open('temp.mp3', 'wb') as f:
        f.write(response['AudioStream'].read())


def play_audio_file_bg(file_path):
    pygame.mixer.init()
    pygame.mixer.music.load(file_path)
    pygame.mixer.music.play()

def play_audio_file(file_path):
    pygame.mixer.init()
    pygame.mixer.music.load(file_path)
    pygame.mixer.music.play()

    # Wait until the audio playback is complete
    while pygame.mixer.music.get_busy():
        pass

def play_audio_file_loop(file_path):
    pygame.mixer.init()
    pygame.mixer.music.load(file_path)

    # Start playing the audio file in a loop
    pygame.mixer.music.play(-1)

def fade_out_audio(duration):
    pygame.mixer.music.fadeout(duration * 1000)  # Fade out over the specified duration in milliseconds

def startup_sound():
    if startup_sound_state == 1:
        play_audio_file("startup.wav")

def get_chatGPT_answer(prompt, model="gpt-3.5-turbo"):
    messages = [{"role": "user", "content": prompt}]
    response = openai.ChatCompletion.create(model=model, messages=messages, temperature=0)
    return response.choices[0].message["content"]

def listen_for_activation_phrase(recognizer, microphone):
    with microphone as source:
        print("Listening...")
        #audio = recognizer.listen(source, timeout=5)
        audio = recognizer.record(source, duration=3)

    try:
        recognized_text = recognizer.recognize_google(audio)
        word_list = recognized_text.split()
        print(word_list)

        for word in word_list:
            if word.lower() == ACTIVATION_WORD:
                print(f"Activation phrase '{ACTIVATION_WORD}' recognized!")
                play_audio_file_bg("listening sound.wav")
                return True
    except sr.UnknownValueError:
        pass
    return False



def listen_for_command(recognizer, microphone):
    with microphone as source:
        print("Listening for command...")
        audio = recognizer.listen(source)

    try:
        # try recognizing the speech in the recording
        # if the speech is unintelligible, `UnknownValueError` will be thrown
        audio_data = audio.get_raw_data()

        # Save the audio as a WAV file
        with wave.open("temp_rec.wav", "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 2 bytes per sample
            wav_file.setframerate(audio.sample_rate)  # Use original sample rate
            wav_file.writeframes(audio_data)

        audio_file = open("temp_rec.wav", "rb")
        text = openai.Audio.transcribe("whisper-1", audio_file)
        print(text)
        print(text['text'])
        command = text['text']

        if command == "":
            print("Couldn't understand the command")
            play_audio_file('nicht_verstanden.mp3')


        return command
    except sr.UnknownValueError:
        print("Couldn't understand the command")
        play_audio_file('nicht_verstanden.mp3')

    return None


def main():
    recognizer = sr.Recognizer()
    microphone = sr.Microphone()
    #microphone = sr.Microphone(device_index=1) # uncomment when using a rasperry pi and set correct device index id

    while True:
        if listen_for_activation_phrase(recognizer, microphone):
            command = listen_for_command(recognizer, microphone)
            if command:
                # play proccessing audio in loop
                play_audio_thread = threading.Thread(target=play_audio_file_loop, args=('processing_audio.wav',))
                play_audio_thread.start()

                print(f"You said: {command}")
                print("ChatGPT is running...")
                try:
                    gpt_response = get_chatGPT_answer(command)
                    print(gpt_response)
                except Exception:
                    fade_out_audio(1)
                    play_audio_thread.join()
                    play_audio_file('leider kein kontakt zu chatgpt.mp3')
                    gpt_response = None

                if gpt_response != None:
                    fade_out_audio(1)
                    play_audio_thread.join()
                    try:
                        convert_text_to_speech(gpt_response)
                        play_audio_thread.join()
                        # play audio file and delete afterwards
                        play_audio_file("temp.mp3")
                        os.remove("temp.mp3")
                    except Exception:
                        play_audio_file('leider kein kontakt zu amazon polly.mp3')
                # Process your command here


if __name__ == "__main__":
    startup_sound()
    startup_sound_state = 0
    main()
