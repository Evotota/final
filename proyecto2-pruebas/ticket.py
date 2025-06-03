import os
import json
import requests
from dotenv import load_dotenv, set_key
from auth import Authorization


def mistokens():

    try:
        with open("config.json", "r") as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ Error al leer config.json: {e}")
        return None

    usuario = config.get("usuario")
    clave = config.get("clave")
    host = config.get("host")
    puerto = config.get("puerto")

    if not all([usuario, clave, host, puerto]):
        print("❌ Configuración incompleta en config.json")
        return None

    url_login = f"https://{host}:{puerto}/api2/json/access/ticket"

    datos = {
        "username": usuario,
        "password": clave
    }

    cabeceras = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    # Ruta al certificado SSL
    cert_path = os.path.join(os.path.dirname(__file__), 'pve-ssl.pem')
    print(f"📄 Ruta absoluta del certificado: {os.path.abspath(cert_path)}")

    print(f"🔐 Usando certificado: {cert_path}")

    if not os.path.exists(cert_path):
        print("❌ Certificado no encontrado")
        return None

    try:
        respuesta = requests.post(
            url_login,
            data=datos,
            headers=cabeceras,
            verify=cert_path  # ✅ Uso del certificado SSL
        )

        if respuesta.status_code == 200:
            try:
                datos_respuesta = respuesta.json()
                if "data" in datos_respuesta and datos_respuesta["data"]:
                    PVE_TICKET = datos_respuesta["data"]["ticket"]
                    PVE_CSRF_TOKEN = datos_respuesta["data"]["CSRFPreventionToken"]
                    username = datos_respuesta["data"]["username"]

                    # Guardar tokens en token.env
                    dotenv_path = os.path.join(os.path.dirname(__file__), "token.env")
                    set_key(dotenv_path, "PVE_ticket", PVE_TICKET)
                    set_key(dotenv_path, "PVE_CSRF_TOKEN", PVE_CSRF_TOKEN)

                    print("✅ Tokens guardados en token.env")

                    # Crear y retornar objeto de autorización
                    return Authorization(
                        user=username or usuario,
                        ticket=PVE_TICKET,
                        CSRFPreventionToken=PVE_CSRF_TOKEN
                    )
                else:
                    print("❌ No se encontró 'data' en la respuesta.")
                    return None
            except json.JSONDecodeError:
                print("❌ La respuesta no es un JSON válido.")
                return None
        else:
            print(f"❌ Código HTTP {respuesta.status_code}: {respuesta.text}")
            return None

    except requests.exceptions.SSLError as ssl_err:
        print(f"🚨 Error SSL: {ssl_err}")
        print("💡 Asegúrate de usar el certificado correcto o prueba con verify=False (solo desarrollo)")
        return None

    except Exception as e:
        print(f"❌ Error general: {str(e)}")
        return None