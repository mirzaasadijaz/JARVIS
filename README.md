# Jarvis-AI: A Voice-Controlled Python Assistant
Jarvis is a desktop virtual assistant built in Python that uses speech recognition and natural language processing to automate web tasks, play music, and provide information. It features a two-tier listening system: a "wake word" mode to stay idle and a "command" mode for active execution.

# 🚀 Key Features
Wake Word Detection: Responds only when it hears "Jarvis" to ensure privacy and efficiency.

Web Automation: Opens over 100+ preset websites (YouTube, GitHub, LinkedIn, etc.) via voice command.

Music Library: A custom library of English and Hindi hits that can be triggered by saying "Play [song name]".

Search Integration: Directly search Google or YouTube using natural language.

News Updates: Fetches the top 5 latest headlines using the NewsAPI.

OpenAI Integration: Fallback support for complex queries using GPT-3.5 Turbo (optional).

Voice Feedback: Uses the SAPI.SpVoice engine for real-time auditory responses.

# 🛠️ Tech Stack
Language: Python 3.x

Speech Recognition: SpeechRecognition (Google Web Speech API)

Text-to-Speech: pywin32 (SAPI5)

API Integrations: OpenAI API, NewsAPI

Browser Control: Python webbrowser module
