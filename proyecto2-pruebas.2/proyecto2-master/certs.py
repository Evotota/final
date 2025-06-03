import os
import ssl

def where():
    """
    Devuelve la ruta del certificado adecuado.
    Prioriza el certificado local 'proxmox.crt'
    """
    current_dir = os.path.dirname(__file__)
    possible_certs = [
        os.path.join(current_dir, "proxmox.crt"),
        '/etc/pve/pve-root-ca.pem',
        '/etc/ssl/certs/ca-certificates.crt'
    ]

    for cert in possible_certs:
        if os.path.isfile(cert):
            return cert

    # Si no se encuentra ninguno, usa el predeterminado del sistema
    default_cert = ssl.get_default_verify_paths().cafile
    if os.path.isfile(default_cert):
        return default_cert

    raise FileNotFoundError("❌ No se encontró un certificado válido.")