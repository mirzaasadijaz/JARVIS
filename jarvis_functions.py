import speech_recognition as sr
import win32com.client
import webbrowser
import music_library
import requests
from site_links import sites
import openai
newsapi = ""
def speak(text):
    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    speaker.Speak(text)

def listen_command(timeout=3, phrase_time_limit=2):
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening...")
        audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=10)
        query = recognizer.recognize_google(audio)
        return query.lower().strip()

openai.api_key = ""

def ask_openai(prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # or "gpt-4" if you have access
            messages=[
                {"role": "system", "content": "You are a virtual assistant named jarvis skilled in general tasks like Alexa and Googlle Could."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.7
        )
        answer = response['choices'][0]['message']['content']
        return answer.strip()
    except Exception as e:
        return f"OpenAI error: {e}"

def processQuery(q):
    q = q.lower().strip()
    print("Processing:", q)
    # speak("You said: " + q)

    for key, url in sites.items():
        if f"open {key}" in q:
            webbrowser.open(url)
            speak(f"Opening {key.capitalize()}.")
            return


    if "search youtube for" in q:
        term = q.replace("search youtube for", "").strip()
        if term:
            webbrowser.open(f"https://www.youtube.com/results?search_query={term.replace(' ', '+')}")
            speak(f"Searching YouTube for {term}")
        else:
            speak("What should I search on YouTube?")

    elif "search google for" in q:
        term = q.replace("search google for", "").strip()
        if term:
            webbrowser.open(f"https://www.google.com/search?q={term.replace(' ', '+')}")
            speak(f"Searching Google for {term}")
        else:
            speak("What should I search on Google?")
    elif q.startswith("play"):
        song = q[5:].strip()
        link = music_library.music.get(song)
        if link:
            webbrowser.open(link)
            speak(f"Playing {song} on YouTube.")
        else:
            speak(f"Sorry, I couldn't find {song} in your library.")

    elif "news" in q:
        speak("Fetching latest news headlines...")
        try:
            r = requests.get(f"https://newsapi.org/v2/top-headlines?country=us&apiKey={newsapi}")
            if r.status_code == 200:
                for article in r.json().get('articles', [])[:5]:
                    speak(article.get('title', 'No title'))
            else:
                speak("Couldn't fetch news. Server error.")
        except Exception as e:
            print("News error:", e)
            speak("Error while fetching news.")

    else:
        speak("You said something outside of my functions.")
        # Optionally fallback to OpenAI here
        # response = ask_openai(q)
        # speak(response)