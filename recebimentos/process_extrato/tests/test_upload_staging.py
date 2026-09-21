from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from upload_staging import stage_uploaded_pdf


@pytest.mark.parametrize('name', ['../original.pdf', '/tmp/original.pdf',
    r'..\original.pdf', r'C:\original.pdf', 'C:original.pdf',
    'folder/file.pdf', '', '..', 'invalid\x00.pdf', 'file.txt'])
def test_upload_paths_are_rejected_without_writes(tmp_path, name):
    staging = tmp_path / 'staging'
    staging.mkdir()
    original = tmp_path / 'original.pdf'
    original.write_bytes(b'original')
    with pytest.raises(ValueError, match='Nome de arquivo'):
        stage_uploaded_pdf(staging, name, b'changed')
    assert original.read_bytes() == b'original'
    assert list(staging.iterdir()) == []


def test_upload_preserves_original_name_and_bytes_and_cleans_temporary_copy(tmp_path):
    original = tmp_path / 'Extrato sintético.PDF'
    original.write_bytes(b'synthetic PDF bytes')
    with TemporaryDirectory(dir=tmp_path) as staging:
        staged = stage_uploaded_pdf(Path(staging), original.name, original.read_bytes())
        assert staged.name == original.name
        assert staged.read_bytes() == original.read_bytes()
        with pytest.raises(FileExistsError):
            stage_uploaded_pdf(Path(staging), original.name, b'replacement')
        assert staged.read_bytes() == original.read_bytes()
    assert not staged.exists()
    assert original.read_bytes() == b'synthetic PDF bytes'


def test_upload_cannot_follow_an_existing_symlink(tmp_path):
    original = tmp_path / 'original.pdf'
    original.write_bytes(b'original')
    staging = tmp_path / 'staging'
    staging.mkdir()
    (staging / 'file.pdf').symlink_to(original)
    with pytest.raises(FileExistsError):
        stage_uploaded_pdf(staging, 'file.pdf', b'replacement')
    assert original.read_bytes() == b'original'
