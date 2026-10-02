import pytest

from app.adapters.local_file_storage import LocalFileStorage

pytestmark = pytest.mark.unit


async def test_saves_reads_and_deletes(tmp_path):
    storage = LocalFileStorage(tmp_path / "output_cvs")

    reference = await storage.save("Ana_CV_Acme_1234.pdf", b"%PDF")

    assert await storage.read(reference) == b"%PDF"
    assert (tmp_path / "output_cvs" / "Ana_CV_Acme_1234.pdf").read_bytes() == b"%PDF"
    await storage.delete(reference)
    assert not (tmp_path / "output_cvs" / reference).exists()


async def test_leaves_no_temporary_files(tmp_path):
    storage = LocalFileStorage(tmp_path)

    await storage.save("cv.pdf", b"%PDF")

    assert [p.name for p in tmp_path.iterdir()] == ["cv.pdf"]


async def test_deleting_a_missing_file_is_not_an_error(tmp_path):
    await LocalFileStorage(tmp_path).delete("nao-existe.pdf")


async def test_reading_a_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        await LocalFileStorage(tmp_path).read("nao-existe.pdf")


@pytest.mark.parametrize(
    "name", ["../fora.pdf", "sub/cv.pdf", "/etc/passwd", "..", ".oculto", "", "cv..pdf"]
)
async def test_refuses_names_that_could_escape_the_folder(tmp_path, name):
    storage = LocalFileStorage(tmp_path / "output_cvs")

    for operation in (storage.save(name, b"x"), storage.read(name), storage.delete(name)):
        with pytest.raises(ValueError):
            await operation


async def test_never_overwrites_an_existing_file(tmp_path):
    storage = LocalFileStorage(tmp_path)
    await storage.save("cv.pdf", b"versao 1")

    with pytest.raises(FileExistsError):
        await storage.save("cv.pdf", b"versao 2")

    assert await storage.read("cv.pdf") == b"versao 1"



async def test_lists_only_regular_files_with_safe_names(tmp_path):
    storage = LocalFileStorage(tmp_path)
    await storage.save("b.pdf", b"x")
    await storage.save("a.pdf", b"x")
    (tmp_path / "subpasta").mkdir()
    (tmp_path / ".oculto").write_bytes(b"x")

    assert await storage.list_names() == ["a.pdf", "b.pdf"]


async def test_listing_a_folder_that_does_not_exist_yet_is_empty(tmp_path):
    assert await LocalFileStorage(tmp_path / "ainda-nao-criada").list_names() == []
