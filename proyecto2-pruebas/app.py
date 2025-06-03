from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import requests
import json
import bcrypt
from dotenv import load_dotenv
import os
from basededatos import db, Usuario, Maquina
from ticket import mistokens
import yaml
import subprocess
#from guacamole import guac



load_dotenv("token.env")# carga los datos del archivo token.env y los guarda en las variables de entorno
load_dotenv("basededatos.env")#carga los datos del archivo basededatos.env y los guarda en las variables de entorno

with open("config.json", "r") as f:
    config = json.load(f)#abre el archivo config.json y lo almacena en la variable config

host = config["host"]#extrae los datos del archivo config.json y los guarda en las variables host
puerto = config["puerto"]#extrae los datos del archivo config.json y los guarda en las variables puerto
STORAGE = config.get("STORAGE")#extrae los datos del archivo config.json y los guarda en las variables storage
node = config.get("NODE")

db_host = os.getenv("MYSQL_HOST")
db_user = os.getenv("MYSQL_USER")
db_password = os.getenv("MYSQL_PASSWORD")
db_name = os.getenv("MYSQL_DB")

app = Flask(__name__)#inicia la aplicacion flask
app.secret_key = os.urandom(24)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_name}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)


auth_tokens = mistokens()#la autenticacion de los tokens los coge de la funcion mistokens del archivo ticket.py

with app.app_context():
    db.create_all()#crea las tablas en la base de datos


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["POST"])
def login():
    if request.method == "POST":
        usuario_input = request.form.get("usuario")
        contrasena_input = request.form.get("contrasena")

    usuario = Usuario.query.filter_by(usuario=usuario_input).first()


    if usuario and bcrypt.checkpw(contrasena_input.encode('utf-8'), usuario.contrasena.encode('utf-8')):
        session['usuario_id'] = usuario.usuarios_id
        session['usuario'] = usuario.usuario
        session['temp_cloudinit_pass'] = contrasena_input
        return redirect(url_for("tusmaquinas"))

    else:
        flash("❌ Usuario o contraseña incorrectos.", "danger")
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

        if len(contrasena) < 6:
            flash("❌ La contraseña debe tener al menos 6 caracteres.", "danger")
            return redirect(url_for("registro"))

        if Usuario.query.filter(db.or_(Usuario.usuario == usuario, Usuario.email == email)).first():
            flash("❌ El nombre de usuario o correo electrónico ya están registrados.", "danger")
            return redirect(url_for("registro"))

        try:
            hashed_password = bcrypt.hashpw(contrasena.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            nuevo_usuario = Usuario(
                nombre=nombre,
                apellido1=apellido1,
                apellido2=apellido2,
                email=email,
                codigo_postal=codigo_postal,
                pais=pais,
                usuario=usuario,
                contrasena=hashed_password
            )

            db.session.add(nuevo_usuario)
            db.session.commit()
            flash("✅ Registro exitoso. Inicia sesión.", "success")
            return redirect(url_for("index"))

        except Exception as e:
            db.session.rollback()
            flash(f"❌ Error al registrar: {str(e)}", "danger")
            return redirect(url_for("registro"))

    return render_template("registro.html")


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
    maquinas_usuario = Maquina.query.filter_by(usuarios_id=usuario_id).all()
    vmids = [m.vmid for m in maquinas_usuario if m.vmid is not None]

    return render_template("tusmaquinas.html", maquinas=maquinas_usuario, vmids=vmids)

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


@app.route("/crear", methods=["POST"])
def crear_maquina():
    if 'usuario_id' not in session:
        return redirect(url_for("index"))

    try:

        nombre_maquina = request.form.get("nombreMaquina").strip()
        so_name = request.form.get("sistema_operativo","").strip()
        ram_input = request.form.get("ram", "8")
        disco_size = request.form.get("disco", "30")
        cpu_cores = int(request.form.get("cpu", "1"))
        ram_mb = int(ram_input) * 1024

        match so_name:
            case "DJellyfish":
                vmid=9001
            case "DNumbat":
                vmid = 9000
            case "SJellyfish":
                vmid = 9001
            case "SNumbat":
                vmid = 9000
            case "rocky8":
                vmid = 9002
            case "rocky9":
                vmid = 9003

        newid = get_next_id()

        nueva_maquina = Maquina(
            vmid=newid,
            nombre=nombre_maquina,
            ram_gb=ram_input,
            disco_gb=disco_size,
            so=so_name,
            cpu_nucleos=cpu_cores,
            usuarios_id=session['usuario_id'],

        )
        db.session.add(nueva_maquina)
        db.session.commit()
        clonar_maquina(nombre_maquina, ram_mb, disco_size, cpu_cores, vmid,newid)
        apps_str = request.form.get('aplicaciones')
        aplicaciones = apps_str.split(",") if apps_str else []
        generar_cloud_init_proxmox(nombre_maquina,aplicaciones,so_name)
        flash("✅ Máquina creada correctamente.", "success")
        return redirect(url_for("tusmaquinas"))


    except Exception as e:
        db.session.rollback()
        flash(f"❌ Error al crear la máquina: {str(e)}", "danger")
        return redirect(url_for("tusmaquinas"))

def clonar_maquina(nombre_maquina, ram_mb, disco_size, cpu_cores, vmid,newid,):
    auth=mistokens()
    disco_size=disco_size
    clon_data={
        "node":"sameva1",
        "vmid": vmid,
        "newid":newid,
    }
    url = f"https://{host}:{puerto}/api2/json/nodes/sameva1/qemu/{vmid}/clone"
    headers = {
        "Authorization": f"PVEAuthCookie={auth.ticket}",
        "CSRFPreventionToken": auth.CSRFPreventionToken,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    response = requests.post(url, data=clon_data, headers=headers, verify='pve-ssl.pem')

    config_data={
        "cicustom": "/snip/snippets/evota-data",
        "node": "sameva1",
        "vmid": newid,
        "name": nombre_maquina,
        "cores": cpu_cores,
        "memory": ram_mb,
    }

    url = f"https://{host}:{puerto}/api2/json/nodes/sameva1/qemu/{newid}/config"
    headers = {
        "Authorization": f"PVEAuthCookie={auth.ticket}",
        "CSRFPreventionToken": auth.CSRFPreventionToken,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    response = requests.post(url, data=config_data, headers=headers, verify='pve-ssl.pem')

    resize_data={
        "disk": "scsi0",
        "node":"sameva1",
        "size":f"{disco_size}G" ,
        "vmid":newid
    }
    url = f"https://{host}:{puerto}/api2/json/nodes/sameva1/qemu/{newid}/resize"
    headers = {
        "Authorization": f"PVEAuthCookie={auth.ticket}",
        "CSRFPreventionToken": auth.CSRFPreventionToken,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    response = requests.put(url, data=resize_data, headers=headers, verify='pve-ssl.pem')


    if response.status_code != 200:
        error_msg = f"Error HTTP {response.status_code}: {response.text}"
        print(f"URL: {url}")
        print(f"Headers: {headers}")
        print(f"Data: {clon_data}")
        raise Exception(error_msg)

    print(f"Máquina {newid} creada correctamente en Proxmox.")


@app.route("/encender/<int:vmid>", methods=["POST"])
def encender(vmid):
    if 'usuario_id' not in session:
        return jsonify({"error": "No autorizado"}), 401

    auth = mistokens()
    url = f"https://{host}:{puerto}/api2/json/nodes/sameva1/qemu/{vmid}/status/start"
    headers = {
        "Cookie": f"PVEAuthCookie={auth.ticket}",
        "CSRFPreventionToken": auth.CSRFPreventionToken,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    response = requests.post(url, headers=headers, verify='pve-ssl.pem')

    if response.status_code == 200:
        flash(f"✅ Máquina {vmid} encendida correctamente.", "success")
    else:
        flash(f"❌ Error al encender la máquina {vmid}: {response.text}", "danger")

    return jsonify({"mensaje": "Acción completada"})



@app.route("/apagar/<int:vmid>", methods=["POST"])
def apagar(vmid):
    if 'usuario_id' not in session:
        return redirect(url_for("index"))

    auth = mistokens()
    vmid = vmid
    url = f"https://{host}:{puerto}/api2/json/nodes/sameva1/qemu/{vmid}/status/stop"

    headers = {
        "Cookie": f"PVEAuthCookie={auth.ticket}",
        "CSRFPreventionToken": auth.CSRFPreventionToken,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    response = requests.post(url, headers=headers, verify='pve-ssl.pem')

    if response.status_code == 200:
        flash(f"✅ Máquina {vmid} apagada correctamente.", "success")
    else:
        flash(f"❌ Error al apagar la máquina {vmid}: {response.text}", "danger")


    return redirect(url_for("tusmaquinas"))

@app.route("/clonar/<int:vmid>",methods=["POST"])
def clonar(vmid):
    if 'usuario_id' not in session:
        return redirect(url_for("index"))

    try:
        newid = get_next_id()
        url_clone = f"https://{host}:{puerto}/api2/json/nodes/sameva1/qemu/{vmid}/clone"

        data = {
            "newid": newid,
            "name": f"copia-{vmid}",
            "full": 1
        }

        headers = {
            "Cookie": f"PVEAuthCookie={auth_tokens.ticket}",
            "CSRFPreventionToken": auth_tokens.CSRFPreventionToken
        }

        response = requests.post(url_clone, data=data, headers=headers, verify='pve-ssl.pem')
        if response.status_code != 200:
            raise Exception(f"Error en API: {response.text}")

        flash(f"✅ Máquina {vmid} clonada como copia-{vmid}", "success")

        original = Maquina.query.filter_by(vmid=vmid).first()
        nueva_maquina = Maquina(
            nombre=f"copia-{vmid}",
            ram_gb=original.ram_gb,
            disco_gb=original.disco_gb,
            so=original.so,
            cpu_nucleos=original.cpu_nucleos,
            usuarios_id=session['usuario_id'],
            vmid=newid
        )
        db.session.add(nueva_maquina)
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        flash(f"❌ Error al clonar la máquina: {str(e)}", "danger")

    return redirect(url_for("tusmaquinas"))



@app.route("/status/<int:vmid>", methods=["get"])
def status(vmid):
    if 'usuario_id' not in session:
        return redirect(url_for("index"))
    auth = mistokens()
    url = f"https://{host}:{puerto}/api2/json/nodes/sameva1/qemu/{vmid}/status"


    headers = {
        "Cookie": f"PVEAuthCookie={auth.ticket}",
        "CSRFPreventionToken": auth.CSRFPreventionToken

    }
    response = requests.get(url,  headers=headers, verify='pve-ssl.pem')

    return response.json()["status"]
def generar_cloud_init_proxmox(nombre_maquina, aplicaciones, so_name):
    print("Generando configuración cloud-init")
    hostname = nombre_maquina
    username = session['usuario']
    password=session['temp_cloudinit_pass']
    filename = f"{username}-data"
    paquetes_base = ['qemu-guest-agent']
    if so_name == "D*":
        paquetes_base = paquetes_base + ["ubuntu-desktop"]
    paquetes_usuario = [app.lower() for app in aplicaciones]  # lowercase solo por ejemplo
    paquetes_finales = paquetes_base + paquetes_usuario
    grupo_sudo = "wheel" if so_name == "rocky*" else "sudo"
    config = {
        'hostname': hostname,
        'manage_etc_hosts': True,
        'chpasswd': {
            'list': [
                f'{username}:{password}'  # Contraseña asignada al usuario
            ],
            'expire': False  # Evita caducidad de contraseña
        },
        'users': [
            {
                'name': username,
                'shell': '/bin/bash',
                'sudo': 'ALL=(ALL) NOPASSWD:ALL',
                'groups': grupo_sudo,
            }
        ],
        "write_files": [
            {
                "path": "/etc/ssh/sshd_config.d/disable-root-login.conf",
                "content": "PermitRootLogin no",
                "owner": "root:root",
                "permissions": "0644"
            }
        ],

        'package_update': True,
        'package_upgrade': True,
        'packages': paquetes_finales,
        'runcmd': [
            'systemctl restart sshd',
        ]
    }

    with open(filename, 'w') as file:
        file.write("#cloud-config\n")
        yaml.dump(config, file, default_flow_style=False, sort_keys=False, explicit_start=False)

    print("Archivo 'user-data' generado exitosamente.")
    scp_copy()

def scp_copy():

    local_path= f"/home/asix1/PycharmProjects/proyecto2-pruebas/{session['usuario']}-data"
    remote_path = "/snip/snippets"
    remote_host = "192.168.12.254"
    remote_user = "root"
    cmd = ["scp",local_path, f"{remote_user}@{remote_host}:{remote_path}"]
    subprocess.run(cmd, check=True)




def crear_usuario_guacamole(usuario, password, first_name, last_name, user_email, vm_ip="127.0.0.1"):
    guac = Guac(url='https://192.168.12.217:8080/guacamole/')
    login = guac.auth('sameva', '1710sameva')  # Credenciales de admin de Guacamole

    if not login:
        raise Exception("❌ No se pudo iniciar sesión en Guacamole")

    # Datos del usuario
    full_name = f"{first_name} {last_name}"

    # 1. Crear usuario
    user_data = {
        "username": usuario,
        "password": password,
        "attributes": {
            "guac-full-name": full_name,
            "guac-email-address": user_email,
            "disabled": "",
            "expired": "",
        }
    }

    created_user = guac.addUser(user_data)
    print(f"✅ Usuario '{usuario}' creado en Guacamole.")

    # 2. Crear conexión RDP
    connection_data = {
        'parentIdentifier': 'ROOT',
        'name': usuario,
        'protocol': 'rdp',
        'parameters': {
            'hostname': vm_ip,
            'port': '3389',
            'username': usuario,
            'password': password,
            'security': 'rdp',
            'ignore-cert': 'true'
        },
        'attributes': {
            'max-connections': None,
            'max-connections-per-user': None
        }
    }

    new_connection = guac.newConnection(connection_data)
    connection_id = new_connection.get("identifier")
    print(f"🔗 Conexión '{usuario}' creada con ID: {connection_id}")

    # 3. Dar permisos al usuario sobre la conexión
    success = guac.givePermissionToConnection(usuario, connection_id)
    if success:
        print(f"🔓 Permisos otorgados a '{usuario}' sobre la conexión.")
    else:
        print(f"⚠️ No se pudieron otorgar permisos a '{usuario}'.")

    return {
        "user": usuario,
        "connection_id": connection_id
    }

def ip():
    auth = mistokens()


    data={
        "node":"sameva1",
        "vmid":100
    }

    url = f"https://{host}:{puerto}/api2/json/node/qemu/sameva1/101"

    headers_auth = {
        "Cookie": f"PVEAuthCookie={auth_tokens.ticket}",
        "CSRFPreventionToken": auth_tokens.CSRFPreventionToken,
    }

    response_next_id = requests.get(url,data=data, headers=headers_auth, verify='pve-ssl.pem')
    return ip()



if __name__ == "__main__":
    app.run(debug=True)
