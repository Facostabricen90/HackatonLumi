import os
import json
from google import genai
from dotenv import load_dotenv
from agent import Agent

load_dotenv()

print("Mi primer agente de IA")

client = genai()
agent = Agent()

while True:
    user_input = input("Tú: ").strip()

    #Validaciones
    if not user_input:
        print("Por favor, ingresa un mensaje.")
        continue

    if user_input.lower() in ["salir", "exit", "quit", "adiós", "bye", "chao"]:
        print("Saliendo del chat. ¡Hasta luego!")
        break

    #Agregar el mensaje del usuario a la lista de mensajes (Historial de conversación)
    agent.messages.append({"role": "user", "content": user_input})

    while True:
        response = client.chat.completions.create(
            model="gemini-3.8-flash",
            messages=agent.messages,
            tools=agent.tools,
        )

        called_tool = agent.process_response(response)
        if not called_tool:
            break