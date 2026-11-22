"""Baixa e extrai os microdados oficiais da PNS 2019 a partir do FTP do IBGE.

Uso (a partir da raiz do projeto):

    python scripts/baixar_dados.py

Os arquivos vão para ``data/raw/`` e são extraídos em ``data/extracted/``.
Os hashes SHA-256 conferem que a versão baixada é a mesma usada no estudo
(microdados de 25/05/2022 e dicionário de 30/05/2022).
"""

import hashlib
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://ftp.ibge.gov.br/PNS/2019/Microdados"
ARQUIVOS = {
    "PNS_2019_20220525.zip": (
        f"{BASE}/Dados/PNS_2019_20220525.zip",
        "a789f6b0cbf6057111939fb3d1fe62ad1d5e848ba9c1f7860d7b44daa4be6057",
    ),
    "Dicionario_e_input_20220530.zip": (
        f"{BASE}/Documentacao/Dicionario_e_input_20220530.zip",
        "bcfed57f8835c07cac38b7343950a500759692974359e007e43217904a2f78da",
    ),
    "Chaves_PNS_2019.pdf": (
        f"{BASE}/Documentacao/Chaves_PNS_2019.pdf",
        "abf8cf0ab09791fa7daa094fd6d1dd332476c6a192428c4e848fb7aa7edb595a",
    ),
}

RAIZ = Path(__file__).resolve().parents[1]
RAW = RAIZ / "data" / "raw"
EXTRAIDOS = RAIZ / "data" / "extracted"


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    EXTRAIDOS.mkdir(parents=True, exist_ok=True)
    for nome, (url, esperado) in ARQUIVOS.items():
        destino = RAW / nome
        if not destino.exists():
            print(f"Baixando {url}")
            urllib.request.urlretrieve(url, destino)
        obtido = sha256(destino)
        if obtido != esperado:
            raise SystemExit(
                f"Hash diferente para {nome}: {obtido}. O IBGE pode ter publicado "
                "uma nova versão; confira o histórico de atualizações antes de seguir."
            )
        print(f"OK  {nome}")
        if nome.endswith(".zip"):
            with zipfile.ZipFile(destino) as z:
                for membro in z.namelist():
                    alvo = (EXTRAIDOS / membro).resolve()
                    if EXTRAIDOS.resolve() not in alvo.parents:
                        raise SystemExit(f"Caminho suspeito dentro do zip: {membro}")
                z.extractall(EXTRAIDOS)
    print(f"Arquivos extraídos em {EXTRAIDOS}")


if __name__ == "__main__":
    main()
