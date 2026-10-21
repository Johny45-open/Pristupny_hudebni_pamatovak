"""Testy statistik — interval vs. celkem, přesné spuštění dialogu."""

from __future__ import annotations

import pytest

from stats import SpravceStatistik, Statistiky


def test_zakladni_pocitadla():
    s = Statistiky()
    assert s.dokoncena_kola == 0
    s.spravne_tony = 3
    s.chybne_tony = 2
    s.uspesna_kola = 1
    s.neuspesna_kola = 1
    assert s.dokoncena_kola == 2


def test_spravny_a_chybny_ton_do_obou_statistik():
    sp = SpravceStatistik(interval_cil=5)
    sp.zaznamenej_spravny_ton()
    sp.zaznamenej_spravny_ton()
    sp.zaznamenej_chybny_ton()
    for s in (sp.celkem, sp.interval):
        assert s.spravne_tony == 2
        assert s.chybne_tony == 1


def test_neplatny_interval():
    with pytest.raises(ValueError):
        SpravceStatistik(interval_cil=0)
    sp = SpravceStatistik(interval_cil=3)
    with pytest.raises(ValueError):
        sp.zmenit_cil_intervalu(-1)


def test_dialog_az_po_presnem_poctu_kol():
    sp = SpravceStatistik(interval_cil=3)
    for i in range(2):
        vysledek = sp.kolo_dokonceno(uspech=(i % 2 == 0))
        assert vysledek is None, "předčasně spuštěný dialog"
    vysledek = sp.kolo_dokonceno(uspech=True)
    assert vysledek is not None
    assert vysledek.pocet_kol == 3
    assert vysledek.interval.dokoncena_kola == 3


def test_snimek_intervalu_a_celkem():
    sp = SpravceStatistik(interval_cil=2)
    sp.zaznamenej_spravny_ton()
    sp.kolo_dokonceno(uspech=True)
    sp.zaznamenej_chybny_ton()
    vysledek = sp.kolo_dokonceno(uspech=False)
    assert vysledek is not None
    assert vysledek.interval.spravne_tony == 1
    assert vysledek.interval.chybne_tony == 1
    assert vysledek.interval.uspesna_kola == 1
    assert vysledek.interval.neuspesna_kola == 1
    assert vysledek.celkem.dokoncena_kola == 2


def test_reset_intervalu_zachova_celkove():
    sp = SpravceStatistik(interval_cil=2)
    sp.zaznamenej_spravny_ton()
    sp.kolo_dokonceno(uspech=True)
    sp.zaznamenej_chybny_ton()
    sp.kolo_dokonceno(uspech=False)
    # Interval byl dokončen a resetován.
    assert sp.interval.dokoncena_kola == 0
    assert sp.interval.spravne_tony == 0
    assert sp.interval.chybne_tony == 0
    # Celkové zůstávají.
    assert sp.celkem.dokoncena_kola == 2
    assert sp.celkem.spravne_tony == 1
    assert sp.celkem.chybne_tony == 1


def test_snimek_se_vrati_prave_jednou():
    """Snímek se vrátí jednou za interval, ne dvakrát pro tentýž interval."""
    sp = SpravceStatistik(interval_cil=2)
    assert sp.kolo_dokonceno(uspech=True) is None
    assert sp.kolo_dokonceno(uspech=True) is not None   # 1. interval hotov
    # Druhé kolo druhého intervalu — zase jen jednou.
    assert sp.kolo_dokonceno(uspech=True) is None
    assert sp.kolo_dokonceno(uspech=True) is not None   # 2. interval hotov


def test_snimek_je_kopie_ne_zive_pocitadlo():
    sp = SpravceStatistik(interval_cil=1)
    sp.zaznamenej_spravny_ton()
    vysledek = sp.kolo_dokonceno(uspech=True)
    hodnota_pred = vysledek.interval.spravne_tony
    sp.zaznamenej_spravny_ton()
    assert vysledek.interval.spravne_tony == hodnota_pred


def test_kolo_dokonceno_pracuje_s_cilist_intervalu():
    sp = SpravceStatistik(interval_cil=10)
    for i in range(10):
        vysledek = sp.kolo_dokonceno(uspech=True)
        if i < 9:
            assert vysledek is None
        else:
            assert vysledek is not None
