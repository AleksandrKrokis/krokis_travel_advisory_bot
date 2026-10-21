import pytest

from bot.sources.news import match_rules


def cats(title: str) -> set[str]:
    return {r[0] for r in match_rules(title)}


@pytest.mark.parametrize("title, expected", [
    ("Estonia requests NATO Article 4 consultations after Russian jets violate airspace", {"article4", "airspace_violation"}),
    ("Eesti taotleb NATO artikli 4 alusel konsultatsioone", {"article4"}),
    ("Эстония инициировала консультации по статье 4 НАТО", {"article4"}),
    ("Three Russian MiG-31 jets violated Estonian airspace for 12 minutes", {"airspace_violation"}),
    ("Нарушение воздушного пространства Эстонии у острова Вайндлоо", {"airspace_violation"}),
    ("Estlink 2 cable damaged, Finnish police detain tanker", {"cable"}),
    ("Soome lahes kahjustati veealust kaablit", {"cable"}),
    ("Russia removes Narva river border buoys", {"narva"}),
    ("Россия сняла буи на реке Нарва", {"narva"}),
    ("Russian troops massing near border with Estonia in Pskov region", {"troops"}),
    ("Government declares state of emergency in Estonia", {"emergency"}),
    ("Valitsus kuulutas välja erakorralise seisukorra", {"emergency"}),
    ("Riigikogu kuulutas välja sõjaseisukorra", {"war_state"}),
    ("В Эстонии объявлено военное положение", {"war_state"}),
    ("President announces general mobilisation", {"ee_mobilisation"}),
    ("Путин объявил мобилизацию в России", {"ru_mobilisation"}),
    ("Russian troops attack Narva", {"attack"}),
    ("NATO invokes Article 5 after attack on Estonia", {"article5"}),
    ("US embassy evacuates families of diplomats", {"embassy_evac"}),
    ("Airspace over Estonia closed to civilian flights", {"airspace_closed"}),
    ("Välisluureamet: Russia could attack NATO within years", {"intel"}),
    ("Major cyberattack hits Estonian government sites", {"cyber"}),
])
def test_positive(title, expected):
    assert cats(title) == expected


@pytest.mark.parametrize("title", [
    "Riigikogu passes amendments to State of War Act",
    "What would happen if Estonia declared martial law?",
    "Exercise: Kaitseliit drills mobilisation of reservists",
    "Cyberattack hits Estonian government websites, no damage",  # cyber only, never "attack"
    "Russia expels Estonian diplomat, embassy staff to leave",
    "Ukraine reports Russian troops massing near Kharkiv border",
    "Tallinn city council approves new budget",
    "Estonia beats Latvia in basketball attack-minded game",
    "Russia announces partial mobilization of reservists",  # partial = 2022-style, Ukraine-focused
    "Ukraine extends martial law for another 90 days, Zelensky declares",
    "Latvia declares state of emergency on Belarus border",
])
def test_negative_decisive(title):
    assert not cats(title) & {"war_state", "emergency", "ee_mobilisation", "attack", "article5",
                              "embassy_evac", "ru_mobilisation"}
