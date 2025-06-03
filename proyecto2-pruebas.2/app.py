from flask import Flask, render_template, request, redirect, url_for, flash, session
import requests
import json
import bcrypt
from dotenv import load_dotenv, set_key
import os
import yaml
import paramiko
from basededatos import db, Usuario, Maquina
from ticket import mistokens
from auth import GuacamoleAuth



load_dotenv("token.env")
load_dotenv("basededatos.env")
load_dotenv("guacamole.env")

with open("config.json", "r") as f:
    config = json.load(f)

host = config["host"]
puerto = config["puerto"]
STORAGE = config.get("STORAGE")
db_host = os.getenv("MYSQL_HOST")
db_user = os.getenv("MYSQL_USER")
db_password = os.getenv("MYSQL_PASSWORD")
db_name = os.getenv("MYSQL_DB")

app = Flask(__name__)
app.secret_key = os.urandom(24)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_name}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)



auth_tokens = mistokens()
with app.app_context():
    db.create_all()


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
            "Cookie": f"PVEAuthCookie={auth.ticket}",
            "CSRFPreventionToken": auth.CSRFPreventionToken
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
        so_name = request.form.get("sistema_operativo", "").strip()
        ram_input = request.form.get("ram", "8")
        disco_size = request.form.get("disco", "30")
        cpu_cores = int(request.form.get("cpu", "1"))
        ram_mb = int(ram_input) * 1024

        match so_name:
            case "DJellyfish": vmid = 9000
            case "DNumbat": vmid = 9001
            case "SJellyfish": vmid = 9002
            case "SNumbat": vmid = 9003
            case "rocky8": vmid = 9004
            case "rocky9": vmid = 9005
            case _: raise Exception("❌ Sistema operativo no reconocido.")

        newid = get_next_id()
        nueva_maquina = Maquina(
            vmid=newid,
            nombre=nombre_maquina,
            ram_gb=ram_input,
            disco_gb=disco_size,
            so=so_name,
            cpu_nucleos=cpu_cores,
            usuarios_id=session['usuario_id'],
            ip=None,

        )
        db.session.add(nueva_maquina)
        db.session.commit()

        clonar_maquina(nombre_maquina, ram_mb, disco_size, cpu_cores, vmid, newid)
        guac_auth = get_guacamole_auth()
        if ip:
            nueva_maquina.ip = ip
            db.session.commit()
            print(f"🔌 IP obtenida y guardada: {ip}")
        else:
            print("⏳ IP aún no disponible")

        flash("✅ Máquina creada correctamente.", "success")
        return redirect(url_for("tusmaquinas"))

    except Exception as e:
        db.session.rollback()
        flash(f"❌ Error al crear la máquina: {str(e)}", "danger")
        return redirect(url_for("tusmaquinas"))
        flash("✅ Máquina creada correctamente.", "success")
        return redirect(url_for("tusmaquinas"))
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Error al crear la máquina: {str(e)}", "danger")
        return redirect(url_for("tusmaquinas"))

def clonar_maquina(nombre_maquina, ram_mb, disco_size, cpu_cores, vmid, newid):
    auth = mistokens()
    node = "pve"
    clon_data = {"node": node, "vmid": vmid, "newid": newid}
    url_clone = f"https://{host}:{puerto}/api2/json/nodes/{node}/qemu/{vmid}/clone"
    headers = {
        "Authorization": f"PVEAuthCookie={auth.ticket}",
        "CSRFPreventionToken": auth.CSRFPreventionToken,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    response = requests.post(url_clone, data=clon_data, headers=headers, verify='pve-ssl.pem')

    config_data = {
        "cicustom": "snip/snippets/samuel.yml",
        "node": node,
        "vmid": newid,
        "name": nombre_maquina,
        "cores": cpu_cores,
        "memory": ram_mb
    }
    url_config = f"https://{host}:{puerto}/api2/json/nodes/{node}/qemu/{newid}/config"
    response = requests.post(url_config, data=config_data, headers=headers, verify='pve-ssl.pem')

    resize_data = {"disk": "scsi0", "node": node, "size": f"{disco_size}G", "vmid": newid}
    url_resize = f"https://{host}:{puerto}/api2/json/nodes/pve/qemu/{newid}/resize"
    response = requests.put(url_resize, data=resize_data, headers=headers, verify='pve-ssl.pem')

    if response.status_code != 200:
        error_msg = f"Error HTTP {response.status_code}: {response.text}"
        print(f"URL: {url_resize}\nHeaders: {headers}\nData: {resize_data}")
        raise Exception(error_msg)

    print(f"Máquina {newid} creada correctamente en Proxmox.")

@app.route("/encender/<int:vmid>", methods=["POST"])
@app.route("/apagar/<int:vmid>", methods=["POST"])
def apagar_encender(vmid):
    if 'usuario_id' not in session:
        return redirect(url_for("index"))
    accion = request.url_rule.rule.split("/")[-2]
    accion_completa = "stop" if accion == "apagar" else "start"
    auth = mistokens()
    node = "pve"
    url = f"https://{host}:{puerto}/api2/json/nodes/{node}/qemu/{vmid}/status/{accion_completa}"
    headers = {
        "Cookie": f"PVEAuthCookie={auth.ticket}",
        "CSRFPreventionToken": auth.CSRFPreventionToken,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    response = requests.post(url, headers=headers, verify='pve-ssl.pem')
    ip(node, vmid)
    if response.status_code != 200:
        error_msg = f"Error HTTP {response.status_code}: {response.text}"
        print(f"URL: {url}\nHeaders: {headers}")
        raise Exception(error_msg)
    flash(f"✅ Máquina {vmid} {accion} correctamente.", "success")
    return redirect(url_for("tusmaquinas"))
    mensaje_accion = "apagada" if accion == "apagar" else "encendida"
    if response.status_code == 200:
        flash(f"✅ Máquina {vmid} {mensaje_accion} correctamente.", "success")
    else:
        flash(f"❌ Error al {accion} la máquina {vmid}: {response.text}", "danger")
    return redirect(url_for("tusmaquinas"))

@app.route("/clonar/<int:vmid>", methods=["POST"])
def clonar(vmid):
    if 'usuario_id' not in session:
        return redirect(url_for("index"))
    try:
        newid = get_next_id()
        node = "pve"
        url_clone = f"https://{host}:{puerto}/api2/json/nodes/{node}/qemu/{vmid}/clone"
        data = {"newid": newid, "name": f"copia-{vmid}", "full": 1}
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
    node = "pve"
    url = f"https://{host}:{puerto}/api2/json/nodes/{node}/qemu/{vmid}/status"
    headers = {
        "Cookie": f"PVEAuthCookie={auth.ticket}",
        "CSRFPreventionToken": auth.CSRFPreventionToken
    }
    response = requests.get(url, headers=headers, verify='pve-ssl.pem')
    return response.json()["status"]

@app.route("/acceder/<int:vmid>")
def acceder_vnc(vmid):
    maquina = Maquina.query.filter_by(vmid=vmid).first()
    if not maquina or not maquina.ip:
        flash("❌ No se encontró la IP de la máquina.", "danger")
        return redirect(url_for("tusmaquinas"))

    try:
        guac_auth = get_guacamole_auth()
        connection_id = create_temporary_vnc_connection_in_guacamole(
            name=f"VM-{vmid}",
            hostname=maquina.ip
        )
        guacamole_url = f"https://192.168.1.62/guacamole/#/client/{connection_id}?token={guac_auth.token}"
        return redirect(guacamole_url)

    except Exception as e:
        flash(f"❌ Error al conectar con Guacamole: {str(e)}", "danger")
        return redirect(url_for("tusmaquinas"))

def get_guacamole_auth():
    token = get_guacamole_token()
    with open("config.json") as f:
        conf = json.load(f)
    usuario = conf.get("usuario_guacamole", "sameva")
    return GuacamoleAuth(user=usuario, token=token)

def get_guacamole_token():
    load_dotenv("guacamole.env")
    token = os.getenv("GUACAMOLE_TOKEN")
    if not token or not is_guacamole_token_valid(token):
        print("🔄 Refrescando token de Guacamole...")
        token = token_guacamole()
        print("✅ Nuevo token generado.")
    return token

def is_guacamole_token_valid(token, base_url="https://192.168.1.62:8443"):
    test_url = f"{base_url}/api/session/data/postgresql/users"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(test_url, headers=headers, verify=False)
        return response.status_code in [200, 201]
    except:
        return False

def token_guacamole(base_url="https://192.168.1.62:8443"):
    url = f"{base_url}/api/tokens"
    payload = {
        "username": config.get("usuario_guacamole"),
        "password": config.get("password_guacamole")
    }
    try:
        response = requests.post(url, data=payload, verify=False)
        response.raise_for_status()
        if response.status_code == 200:
            auth_token = response.json().get("authToken")
            if not auth_token:
                raise Exception("❌ No se pudo obtener el token.")
            dotenv_path = os.path.join(os.path.dirname(__file__), "guacamole.env")
            os.makedirs(os.path.dirname(dotenv_path), exist_ok=True)
            set_key(dotenv_path, "GUACAMOLE_TOKEN", auth_token)
            print("✅ Token guardado correctamente.")
            return auth_token
        else:
            raise Exception(f"❌ Código HTTP {response.status_code}: {response.text}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"❌ Error al obtener el token: {e}")


def create_vnc_connection_guacamole(name, hostname, token, port=5900, data_source="mysql"):
    token = get_guacamole_token()
    name = f"VM-{vmid}"
    base_url = "https://192.168.1.62:8443"
    url = "http://192.168.1.40/guacamole/api/connections"

    payload = {
        "parentIdentifier": "ROOT",
        "name": name,
        "protocol": "vnc",
        "parameters": {
            "hostname": hostname,
            "port": str(port),
            "password": ""  # opcional, si usas credenciales
        },
        "attributes": {}
    }

    headers = {
         "Authorization": f"Bearer {token}"
    }

    url = f"{base_url}/api/session/data/postgresql/connections"
    response = requests.post(url, json=payload, headers=headers, verify=False)

    if response.status_code == 201:
        connection_id = response.json()["identifier"]
        return connection_id
    else:
        raise Exception(f"❌ Error al crear conexión en Guacamole: {response.text}")

def generar_cloud_init_proxmox(nombre_maquina, aplicaciones, so_name, ip=None, netmask="255.255.255.0", gateway="192.168.1.1", dns="8.8.8.8"):
    print("📄 Generando configuración cloud-init")
    username = session['usuario']
    password = session['temp_cloudinit_pass']
    filename = f"{username}-data"

    paquetes_base = ['qemu-guest-agent']
    grupo_sudo = "wheel" if "rocky" in so_name.lower() else "sudo"
    paquetes_usuario = [app.lower() for app in aplicaciones]
    paquetes_finales = paquetes_base + paquetes_usuario

    config = {
        'hostname': nombre_maquina,
        'manage_etc_hosts': True,
        'chpasswd': {'list': [f'{username}:{password}'], 'expire': False},
        'users': [{
            'name': username,
            'shell': '/bin/bash',
            'sudo': 'ALL=(ALL) NOPASSWD:ALL',
            'groups': grupo_sudo,
        }],
        "write_files": [{
            "path": "/etc/ssh/sshd_config.d/disable-root-login.conf",
            "content": "PermitRootLogin no\n",
            "owner": "root:root",
            "permissions": "0644"
        }],
        'package_update': True,
        'package_upgrade': True,
        'packages': paquetes_finales,
        'runcmd': ['systemctl restart sshd'],
    }

    if ip:
        config['network'] = {
            'version': 2,
            'ethernets': {
                'enp0s3': {
                    'dhcp4': False,
                    'addresses': ["192.168.1.220/24"],
                    'gateway4': gateway,
                    'nameservers': {
                        'addresses': [dns]
                    }
                }
            }
        }

    with open(filename, 'w') as file:
        file.write("#cloud-config\n")
        yaml.dump(config, file, default_flow_style=False, sort_keys=False, explicit_start=False)

    print("✅ Archivo 'user-data' generado exitosamente.")
    scp_copy()

def scp_copy():
    hostname = "192.168.1.63"
    port = 22
    username = "root"
    password = session.get('temp_cloudinit_pass')
    local_path = f"/home/evota/PycharmProjects/proyecto2-pruebas/{session['usuario']}-data"
    remote_path = "/snip/snippets"

    try:
        transport = paramiko.Transport((hostname, port))
        transport.connect(username=username, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)

        def upload_folder(sftp_client, local_folder, remote_folder):
            for root, dirs, files in os.walk(local_folder):
                relative_path = os.path.relpath(root, local_folder)
                remote_dir = os.path.join(remote_folder, relative_path).replace("\\", "/")
                try:
                    sftp_client.stat(remote_dir)
                except FileNotFoundError:
                    sftp_client.mkdir(remote_dir)
                for file in files:
                    local_file = os.path.join(root, file)
                    remote_file = os.path.join(remote_dir, file)
                    sftp_client.put(local_file, remote_file)
                    print(f"📤 Subido: {local_file} -> {remote_file}")
            sftp_client.close()
            transport.close()
        upload_folder(sftp, local_path, remote_path)
        print("✅ Carpeta subida correctamente.")
    except Exception as e:
        print(f"❌ Error al subir carpeta: {e}")

def ip():
    auth = mistokens()
    url = f"https://{host}:{puerto}/api2/json/nodes/pve/qemu/102/agent/network-get-interfaces"

    headers = {
        "Cookie": f"PVEAuthCookie={auth.ticket}",
        "CSRFPreventionToken": auth.CSRFPreventionToken,
        "Content-Type": "application/x-www-form-urlencoded"
    }


    response = requests.get(url, headers=headers, verify='pve-ssl.pem')

    if response.status_code == 200:
        data = response.json()["data"]
        for interface in data:
            ip_info = interface.get("ip-addresses", [])
            for ip_data in ip_info:
                 if ip_data["ip-address-type"] == "ipv4":
                     ip = ip_data["ip-address"]
                     print(f"🔌 IP obtenida via QEMU Guest Agent: {ip}")
                     return ip


        else:
            print(f"❌ Error en agent: {response.status_code} - {response.text}")






if __name__ == "__main__":
    app.run(debug=True)