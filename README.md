# HackatonLumi

##Instalaciones necesarias - pip install

## Fuente de datos

El agente consulta exclusivamente en vivo el dataset oficial de IPS de datos.gov.co: `s2ru-bqt6`. La aplicación no carga `ips.json`, no descarga el dataset completo y calcula conteos y capacidad mediante consultas SoQL (`$select`, `$where`, `$limit` y `$order`).

Variables de entorno:

```text
GEMINI_API_KEY=...
SOCRATA_APP_TOKEN=...
SOCRATA_DATASET_API_URL=https://www.datos.gov.co/resource/s2ru-bqt6.json
FRONTEND_ORIGINS=https://tu-proyecto.vercel.app
```

`SOCRATA_APP_TOKEN` es opcional, pero recomendable para producción. `FRONTEND_ORIGINS` debe contener el dominio final de Vercel; durante desarrollo puede ser `*`.

## Ejecución local

Instala las dependencias con:

```powershell
& ".\LumiEnv313\Scripts\python.exe" -m pip install -r requirements.txt
```

La aplicación FastAPI se ejecuta como función serverless en Vercel. Para una previsualización estática local puedes servir `public/`, pero las rutas `/api/sesion` y `/api/consulta` requieren el despliegue de Vercel.

## Despliegue en Vercel

El directorio `public/` contiene la interfaz y `api/index.py` expone FastAPI como función serverless. En Vercel, selecciona este repositorio, configura las variables de `.env.example` en Project Settings y despliega sin un comando de build. El frontend conservará las rutas `/api/sesion` y `/api/consulta` en el mismo dominio.