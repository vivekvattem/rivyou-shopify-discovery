from rivyou.extract.location import extract_location


def test_city_maps_to_state():
    assert extract_location("Visit us in Bangalore").state == "Karnataka"


def test_explicit_state_is_detected():
    assert extract_location("Ernakulam, Kerala 682001").state == "Kerala"


def test_weak_unknown_location_returns_none():
    assert extract_location("We ship beautiful products worldwide").state is None
