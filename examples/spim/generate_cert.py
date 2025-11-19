"""Generate self-signed SSL certificates for local development."""

import subprocess
import sys
from pathlib import Path


def generate_self_signed_cert(cert_file: Path, key_file: Path):
    """Generate a self-signed certificate using OpenSSL."""
    print(f"Generating self-signed certificate...")
    print(f"  Cert: {cert_file}")
    print(f"  Key:  {key_file}")

    cmd = [
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:4096",
        "-keyout",
        str(key_file),
        "-out",
        str(cert_file),
        "-days",
        "365",
        "-nodes",
        "-subj",
        "/CN=localhost",
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print("✓ Certificate generated successfully.")
    except subprocess.CalledProcessError as e:
        print("Error generating certificate:")
        print(e.stderr.decode())
        sys.exit(1)
    except FileNotFoundError:
        print("Error: 'openssl' command not found. Please install OpenSSL.")
        sys.exit(1)


if __name__ == "__main__":
    output_dir = Path(__file__).parent
    cert_path = output_dir / "cert.pem"
    key_path = output_dir / "key.pem"

    generate_self_signed_cert(cert_path, key_path)
