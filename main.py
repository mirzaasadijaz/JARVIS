from jarvis_functions import speak, listen_command, processQuery, sr

if __name__ == "__main__":
    speak("Initializing Jarvis...")

    try:
        while True:
            # Keep listening until wake word is detected
            query = None
            while True:
                try:
                    query = listen_command(timeout=3, phrase_time_limit=2)
                    print("You said:", query)

                    if query == "jarvis":
                        speak("Yes, I am here. How can I help you?")
                        break  # Exit the inner loop and start processing commands
                    else:
                        print("Waiting for wake word 'jarvis'...")

                except sr.WaitTimeoutError:
                    print("No speech detected.")
                except sr.UnknownValueError:
                    print("Could not understand audio.")
                except Exception as e:
                    print("Error while waiting for wake word:", e)

            # Now Jarvis is active
            while True:
                try:
                    command = listen_command(timeout=3, phrase_time_limit=8)
                    print("Command:", command)

                    if "go to hell" in command:
                        speak("Goodbye! Shutting down.")
                        exit()

                    processQuery(command)

                except sr.WaitTimeoutError:
                    print("No command heard.")
                except sr.UnknownValueError:
                    print("Could not understand the command.")
                except Exception as e:
                    print("Error while processing command:", e)

    except KeyboardInterrupt:
        speak("Exiting Jarvis.")
