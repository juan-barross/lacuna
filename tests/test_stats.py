import pytest

from dxp.stats import latency_summary, wilson


def test_wilson():
    low, high = wilson(50, 100)

    assert low == pytest.approx(0.404, abs=1e-3)
    assert high == pytest.approx(0.596, abs=1e-3)


def test_wilson_sem_amostra():
    assert wilson(0, 0) == (0.0, 0.0)


@pytest.mark.parametrize(("hits", "n"), [(0, 10), (10, 10)])
def test_wilson_nos_extremos_fica_entre_zero_e_um(hits, n):
    low, high = wilson(hits, n)

    assert 0.0 <= low <= high <= 1.0


def test_latency_summary_ordena_antes_de_calcular():
    seconds = [10.0, 10.0] + [1.0] * 18

    assert latency_summary(seconds) == {"latencia_p50_s": 1.0, "latencia_p95_s": 10.0}
