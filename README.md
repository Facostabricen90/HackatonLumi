# HackatonLumi

##Instalaciones necesarias - pip install
- google-genai 
- pyaudio
- python-dotenv

## Interfaz web

Para probar la interfaz clara de voz y sesiones, inicia un servidor local desde la carpeta del proyecto:

```powershell
& ".\LumiEnv313\Scripts\python.exe" -m http.server 8081
```

Abre `http://localhost:8081` en el navegador. La entrada de voz usa la API de reconocimiento de voz del navegador cuando está disponible.