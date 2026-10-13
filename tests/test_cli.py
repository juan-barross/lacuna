from dxp.cli import RECORTE, load_recorte


def test_recorte_versionado_tem_19_municipios():
    ids = load_recorte(RECORTE)
    assert len(ids) == 19
    assert "3304557" in ids
    assert "3302700" not in ids
