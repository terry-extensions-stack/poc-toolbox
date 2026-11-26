import json
import os
import tempfile

from pathlib import Path
from uuid import UUID


def save_receipt(directory: Path, job_id: UUID, index: int, provider_id: str) -> None:
    receipt = {'job_id': str(job_id), 'index': index, 'provider_id': provider_id}
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory, delete=False) as output:
        temporary = Path(output.name)
        try:
            json.dump(receipt, output)
            output.flush()
            os.fsync(output.fileno())
        except BaseException:
            output.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(directory / f'provider-{index}.json')
    finally:
        temporary.unlink(missing_ok=True)


def read_receipt(directory: Path, job_id: UUID, index: int) -> str | None:
    path = directory / f'provider-{index}.json'
    if not path.exists():
        return None
    receipt = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(receipt, dict) or receipt.get('job_id') != str(job_id) or receipt.get('index') != index:
        raise ValueError('Provider receipt does not match this job and segment')
    provider_id = receipt.get('provider_id')
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise ValueError('Provider receipt has no valid task ID')
    return provider_id
