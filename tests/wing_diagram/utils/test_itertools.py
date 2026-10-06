import pytest

from wing_diagram.util.itertools import rest, only


def test_rest_no_elements():
    with pytest.raises(ValueError):
        rest([])


def test_rest_elements():
    assert list(rest([1,2,3,4])) == [2, 3, 4]

def test_only():
    assert only(["blah"]) == "blah"

    with pytest.raises(ValueError) as err:
        _ = only([1, 2])
    assert err.value.args[0] == "only: More than one element"

    with pytest.raises(ValueError) as err:
        _ = only([])
    assert err.value.args[0] == "only: none found"

