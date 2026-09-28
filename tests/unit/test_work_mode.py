import pytest

from app.domain.models import WorkMode, detect_work_mode

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # casos reais vistos no LinkedIn
        ("Staff Backend Engineer – Python - Trabalho Remoto", WorkMode.REMOTE),
        ("Principal Backend Engineer (Python) - Trabalho Remoto", WorkMode.REMOTE),
        # variações de escrita
        ("Dev Python 100% Remoto", WorkMode.REMOTE),
        ("Python Developer (Remote)", WorkMode.REMOTE),
        ("Analista de Dados - Home Office", WorkMode.REMOTE),
        ("Engenheira de Dados Remota", WorkMode.REMOTE),
        ("Dev Backend - HÍBRIDO", WorkMode.HYBRID),
        ("Backend Engineer, Hybrid", WorkMode.HYBRID),
        ("Desenvolvedor Java Presencial", WorkMode.ONSITE),
        ("QA Engineer (On-site)", WorkMode.ONSITE),
        # local também declara o modo
        ("Python Developer Remote, Brazil", WorkMode.REMOTE),
        # mais de um modo
        ("Dev Python - Remoto ou Híbrido", WorkMode.HYBRID),
        ("Dev Python - Presencial ou Remoto", WorkMode.UNKNOWN),
        # sem declaração
        ("Senior Python Developer", WorkMode.UNKNOWN),
        ("", WorkMode.UNKNOWN),
    ],
)
def test_detects_declared_work_mode(text, expected):
    assert detect_work_mode(text) is expected


@pytest.mark.parametrize("text", ["Remotely Sensed Data Engineer", "Hybridization Scientist"])
def test_matches_whole_words_only(text):
    assert detect_work_mode(text) is WorkMode.UNKNOWN
