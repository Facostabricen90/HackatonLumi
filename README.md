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

Ejecuta el proyecto completo con la CLI de Vercel:

```powershell
vercel login
vercel dev --listen 8081
```

`vercel login` abre el flujo de autenticación en el navegador. Si aparece un token inválido, ejecuta `vercel logout` y vuelve a hacer `vercel login`. Después abre `http://localhost:8081`; Vercel servirá `public/` y las funciones `/api/sesion` y `/api/consulta` en local, sin `uvicorn`.

Si `vercel dev` falla en Windows con `unicodeescape` dentro de `.vercel/python/vc_init_dev.py`, usa el servidor ASGI local alternativo:

```powershell
& ".\LumiEnv313\Scripts\python.exe" -m pip install -r requirements-dev.txt
& ".\LumiEnv313\Scripts\python.exe" -m hypercorn app:app --bind 127.0.0.1:8081
```

Este error pertenece al runtime local de Vercel; no edites `.vercel/python/vc_init_dev.py` porque es un archivo generado.

## Despliegue en Vercel

El directorio `public/` contiene la interfaz y `api/index.py` expone FastAPI como función serverless. En Vercel, selecciona este repositorio, configura las variables de `.env.example` en Project Settings y despliega sin un comando de build. El frontend conservará las rutas `/api/sesion` y `/api/consulta` en el mismo dominio.