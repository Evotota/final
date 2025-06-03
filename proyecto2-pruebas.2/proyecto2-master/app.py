import auth_token
from flask import Flask, render_template, request, redirect, url_for, flash, session
import pymysql
import requests
import json
import os
from dotenv import load_dotenv
import bcrypt
from ticket import mistokens

load_dotenv("token.env")
load_dotenv("basededatos.env")

with open("config.json", "r") as f:
    config = json.load(f)

host = config["host"]
puerto = config["puerto"]
STORAGE = config.get("storage", "local-lvm")

try:
    auth_tokens = mistokens()
    if auth_tokens and hasattr(auth_tokens, 'ticket'):
        print("🎫 Token generado:", auth_tokens)
    else:
        raise Exception("Los tokens generados no son válidos")
except Exception as e:
    print(f"❌ Error al generar tokens: {str(e)}")
    auth_tokens = None


app = Flask(__name__)
app.secret_key = "clave_secreta_para_usar_flash"

def get_db_connection():
    conn = pymysql.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DB"),
        cursorclass=pymysql.cursors.DictCursor
    )
    return conn


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["POST"])
def login():
    usuario = request.form.get("usuario")
    contrasena_ingresada = request.form.get("contrasena")

    if not usuario or not contrasena_ingresada:
        flash("❌ Campos incompletos.","danger")
        return redirect(url_for("index"))

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM usuarios WHERE usuario=%s", (usuario,))
            user = cur.fetchone()
        conn.close()

        if user and bcrypt.checkpw(contrasena_ingresada.encode('utf-8'), user['contrasena'].encode('utf-8')):
            session['usuario_id'] = user['usuarios_id']
            return redirect(url_for("maquina_virtual"))
        else:
            flash("❌ Usuario o contraseña incorrectos.","danger")
            return redirect(url_for("index"))
    except Exception as e:
        flash(f"❌ Error al iniciar sesión: {str(e)}", "danger")
        return redirect(url_for("index"))


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        apellido1 = request.form.get("apellido1")
        apellido2 = request.form.get("apellido2")
        email = request.form.get("email")
        codigo_postal = request.form.get("codigo_postal")
        pais = request.form.get("pais")
        usuario = request.form.get("usuario")
        contrasena = request.form.get("contrasena")

        if not all([nombre, apellido1, email, usuario, contrasena]):
            flash("❌ Todos los campos obligatorios deben estar completos.", "danger")
            return redirect(url_for("registro"))

        try:
            hashed_password = bcrypt.hashpw(contrasena.encode('utf-8'), bcrypt.gensalt())
            hashed_password_str = hashed_password.decode('utf-8')

            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO usuarios 
                    (nombre, apellido1, apellido2, email, codigo_postal, pais, usuario, contrasena)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    nombre, apellido1, apellido2, email, codigo_postal,
                    pais, usuario, hashed_password_str
                ))
                conn.commit()
            conn.close()
            flash("✅ Registro exitoso. Inicia sesión.", "success")
            return redirect(url_for("index"))

        except pymysql.err.IntegrityError:
            flash("❌ Este usuario ya existe.", "danger")
            return render_template("registro.html")

        except Exception as e:
            flash(f"❌ Error al registrar: {str(e)}", "danger")
            return render_template("registro.html")


    return render_template("registro.html")


@app.route("/maquina_virtual")
def maquina_virtual():
    if 'usuario_id' not in session:
        return redirect(url_for("index"))
    return render_template("tusmaquinas.html")

@app.route("/bton_crear")
def bton_crear():
    if 'usuario_id' not in session:
        return redirect(url_for("index"))
    return render_template("maquinas.html")


@app.route("/tusmaquinas")
def tusmaquinas():
    if 'usuario_id' not in session:
        return redirect(url_for("index"))
    usuario_id = session['usuario_id']

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM maquinas WHERE usuarios_id = %s", (usuario_id,))
            maquinas = cur.fetchall()
        conn.close()

        return render_template("tusmaquinas.html", maquinas=maquinas)


    except Exception as e:
        flash(f"❌ Error al cargar máquinas: {str(e)}", "danger")
        return redirect(url_for("index"))

    print(maquinas)



@app.route("/crear", methods=["POST"])
def crear_maquina():
    if 'usuario_id' not in session:
        return redirect(url_for("index"))

    try:
        nombre = request.form.get("nombreMaquina").strip()
        so_name = request.form.get("sistema_operativo", "Numbat").lower()
        ram_input = request.form.get("ram", "8")
        disco_size = request.form.get("disco", "30")
        cpu_cores = int(request.form.get("cpu", "1"))

        ram_mb = int(ram_input) * 1024
        ram_gb = ram_mb // 1024
        disco_gb = int(disco_size)

        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO maquinas (nombre, ram_gb, disco_gb, usuarios_id, cpu_nucleos, so)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (nombre, ram_gb, disco_gb, session['usuario_id'], cpu_cores, so_name))

            conn.commit()
        try:
            create_vm_in_proxmox(nombre, so_name, ram_mb, disco_gb, cpu_cores)
        except Exception as e:
            flash(f"⚠️ Máquina creada localmente, pero fallo en Proxmox: {str(e)}", "warning")
        flash("✅ Máquina creada correctamente.", "success")

        return redirect(url_for("tusmaquinas"))

    except Exception as e:
        flash(f"❌ Error al crear máquina: {str(e)}", "danger")
        return redirect(url_for("maquina_virtual"))



def get_next_id():
    url_next_id = f"https://{host}:{puerto}/api2/json/cluster/nextid"
    headers_auth = {
        "Cookie": f"PVEAuthCookie={auth_tokens.ticket}",
        "CSRFPreventionToken": auth_tokens.CSRFPreventionToken,
    }

    response_next_id = requests.get(url_next_id, headers=headers_auth, verify='pve-ssl.pem')

    if response_next_id.status_code == 401:
        auth = mistokens()
        if not auth:
            raise Exception("No se pudieron regenerar los tokens")

        headers_auth = {
            "Cookie": f"PVEAuthCookie={auth_tokens.ticket}",
            "CSRFPreventionToken": auth_tokens.CSRFPreventionToken,
        }

        response_next_id = requests.get(url_next_id, headers=headers_auth, verify='pve-ssl.pem')

    if response_next_id.status_code != 200:
        raise Exception(f"Error obteniendo el siguiente ID: {response_next_id.text}")

    return response_next_id.json()["data"]


def create_vm_in_proxmox(nombre, os_name, ram_mb, disk_size, cpu_cores):
    try:
        auth = mistokens()
        vmid = get_next_id()
        node = config["NODE"]

        vm_data = {
            "vmid": vmid,
            "name": str(nombre) ,
            "storage": STORAGE,
            "ostype": "win10" if "windows" in os_name.lower() else "l26",
            "sata0": f"{STORAGE}:{disk_size}",
            "cores": cpu_cores,
            "memory": ram_mb,
            "scsihw": "virtio-scsi-pci",
        }

        headers = {
            "Authorization": f"PVEAuthCookie={auth.ticket}",
            "CSRFPreventionToken": auth.CSRFPreventionToken,
            "Content-Type": "application/x-www-form-urlencoded"
        }

        url = f"https://{host}:{puerto}/api2/json/nodes/{node}/qemu"
        response = requests.post(url, data=vm_data, headers=headers, verify='pve-ssl.pem')
        print("Status Code:", response.status_code)
        print("Response Text:", response.text)

        if response.status_code != 200:
            raise Exception(f"Error HTTP {response.status_code}: {response.text}")


    except Exception as e:
        print(f"❌ Error al crear VM: {e}")
        raise

@app.route("/inicio")
def inicio():
    return render_template("inicio.html")

if __name__ == "__main__":
    app.run(debug=True)