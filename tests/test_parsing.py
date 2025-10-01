from bot.services.parsing import parse_amount_rub_to_kop, AmountParseError


def test_parse_ok():
    assert parse_amount_rub_to_kop("1200") == 120000
    assert parse_amount_rub_to_kop("1 200") == 120000
    assert parse_amount_rub_to_kop("1200.5") == 120050
    assert parse_amount_rub_to_kop("1 200,50") == 120050


def test_parse_invalid():
    for bad in ["", "-1", "abc", "1,200", "12.345", "12."]:
        try:
            parse_amount_rub_to_kop(bad)
            assert False
        except AmountParseError:
            pass
