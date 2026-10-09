import os
import json

class Agent:
    def __init__(self, name):
        self.setup_tools()
        self.messages = [
            {"role": "system", "content": "Eres un agente de IA útil y amigable, que habla español y eres muy conciso con tus respuestas."}
        ]

    def setup_tools(self):
        self.tools = [
            {
                "type": "function",
                "name": "list_files_in_dir",
                "description": "Lista los archivos en un directorio dado.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directory": {
                            "type": "string",
                            "description": "El directorio para listar los archivos. Por defecto es el directorio actual."
                        }
                    },
                    "required": []
                }
            },
            {
                "type": "function",
                "name": "read_file",
                "description": "Lee el contenido de un archivo en una ruta especificada",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "La ruta del archivo que se desea leer"
                        }
                    },
                    "required": ["path"]
                }
            },
            {
                "type": "function",
                "name": "edit_file",
                "description": "Edita el contenido de un archivo reemplazando un contenido antiguo por uno nuevo. Si el archivo no existe, lo crea.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "La ruta del archivo que se desea editar, o crear si no existe"
                        },
                        "old_content": {
                            "type": "string",
                            "description": "El contenido antiguo que se desea reemplazar (puede ser vacio para crear un archivo nuevo con el contenido nuevo)"
                        },
                        "new_content": {
                            "type": "string",
                            "description": "El nuevo contenido que reemplazará al antiguo (O el texto para un archivo nuevo)"
                        }
                    },
                    "required": ["path", "new_content"]
                }
            }
        ]

    #Definicion de herramientas
    def list_files_in_dir(directory="."):
        print("⚙️ Herramienta llamada: list_files_in_dir")
        try:
            files = os.listdir(directory)
            return {"Files": files}
        except Exception as e:
            return {"Error": str(e)}

    def read_file(self, path):
        print("⚙️ Herramienta llamada: read_file")
        try:
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
        except Exception as e:
            contentError = f"Error al leer el archivo: {path}"
            print(contentError)
            return contentError

    def edit_file(self, path, old_content, new_content):
        print("⚙️ Herramienta llamada: edit_file")
        try:
            enable_file = os.path.exists(path)
            if enable_file:
                content = self.read_file(path)
                if old_content not in content:
                    return f"El contenido '{old_content}' no se encontró en el archivo: {path}"
                content = content.replace(old_content, new_content)
            else:
                #Crear o sobreescribir el archivo si no existe
                dir_name = os.path.dirname(path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
                content = new_content

            with open(path, 'w', encoding='utf-8') as file:
                file.write(content)
            action = "editado" if enable_file else "creado"
            print(f"Archivo {path} {action} exitosamente!")
        except Exception as e:
            contentError = f"Error al editar el archivo: {path}"
            print(contentError)
            return contentError

    def process_response(self, response):
        #True= si llama a una funcion, False= No hubo llamado
        self.messages += response.output
        
        for output in response.output:
            if output.type == "function_call":
                fn_name = output.name
                args = json.loads(output.arguments)
                
                print (f"    - Agente de IA considera el llamdo a la función: {fn_name}")
                print(f"    -  Argumentos: {args}")

                if fn_name == "list_files_in_dir":
                    result = self.list_files_in_dir(**args)
                elif fn_name == "read_file":
                    result = self.read_file(**args)
                elif fn_name == "edit_file":
                    result = self.edit_file(**args)

                #Agregar la respuesta de la función al historial de mensajes
                self.messages.append({
                    "type": "function_call_output",
                    "call_id": output.call_id,
                    "output": json.dumps({
                        "files": result
                    })
                })
                return True
            elif output.type == "message":
                print(f"    - Agente de IA: {output.content}")

        return False
