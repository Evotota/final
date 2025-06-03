from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class Usuario(db.Model):
    __tablename__ = 'usuarios'

    usuarios_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(50))
    apellido1 = db.Column(db.String(50))
    apellido2 = db.Column(db.String(50))
    email = db.Column(db.String(100))
    codigo_postal = db.Column(db.String(10))
    pais = db.Column(db.String(50))
    usuario = db.Column(db.String(50), unique=True, nullable=False)
    contrasena = db.Column(db.String(255), nullable=False)

    maquinas = db.relationship('Maquina', backref='propietario', lazy=True)


class Maquina(db.Model):
    __tablename__ = 'maquinas'

    id_maquina = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    vmid = db.Column(db.Integer, unique=True,nullable=False)
    nombre = db.Column(db.String(255), nullable=False)
    ram_gb = db.Column(db.Integer, nullable=False)
    disco_gb = db.Column(db.Integer, nullable=False)
    cpu_nucleos = db.Column(db.Integer, nullable=False)
    so = db.Column(db.String(50), nullable=False)
    ip = db.Column(db.String(15))


    usuarios_id = db.Column(db.Integer, db.ForeignKey('usuarios.usuarios_id'), nullable=False)