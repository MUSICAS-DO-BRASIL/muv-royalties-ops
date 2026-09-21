"""Stage uploaded PDFs without accepting client-controlled filesystem paths."""
from pathlib import Path, PureWindowsPath


def stage_uploaded_pdf(directory: Path, name: str, content: bytes) -> Path:
    if (not name or name in ('.', '..') or '/' in name or '\\' in name
            or ':' in name or '\x00' in name or PureWindowsPath(name).drive
            or Path(name).suffix.lower() != '.pdf'):
        raise ValueError('Nome de arquivo inválido: envie um PDF sem caminho de pasta.')
    target = directory / name
    # Exclusive creation also refuses existing files and symbolic links.
    with target.open('xb') as output:
        output.write(content)
    return target
