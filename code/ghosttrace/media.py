"""Local PDF extraction and screenshot OCR with content-addressed caching."""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


def extract(path, cache):
    path, cache = Path(path), Path(cache)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    destination = cache / (digest + '.json')
    if destination.exists():
        return {**json.loads(destination.read_text(encoding='utf-8')), 'cache_hit': True}
    if path.suffix.lower() == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(path)
        result = {'method': 'pypdf', 'text': '\n'.join(page.extract_text() or '' for page in reader.pages), 'pages': len(reader.pages)}
    elif os.name == 'nt':
        command = ['powershell.exe', '-NoProfile', '-File', str(Path(__file__).with_name('ocr_windows.ps1')), '-ImagePath', str(path.resolve())]
        completed = subprocess.run(command, capture_output=True, encoding='utf-8', errors='replace', timeout=90)
        if completed.returncode:
            raise RuntimeError('Windows OCR failed: ' + completed.stderr[:300])
        result = {'method': 'Windows.Media.Ocr.OcrEngine/en-US', 'text': completed.stdout}
    elif shutil.which('tesseract'):
        completed = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'eng'], capture_output=True, encoding='utf-8', timeout=90, check=True)
        result = {'method': 'Tesseract/eng', 'text': completed.stdout}
    else:
        raise RuntimeError('Screenshot OCR requires Windows English OCR or Tesseract installed on PATH.')
    result['sha256'] = digest
    cache.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    return {**result, 'cache_hit': False}
