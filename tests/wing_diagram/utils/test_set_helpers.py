from wing_diagram.util.set_helpers import find_differences

def test_find_differences() -> None:

    group1 = [1, 2, 3, 4]
    group2 = [3.0, 4.0, 5.0, 6.0]

    differences = find_differences(group1, lambda i: f"{i:d}", group2, lambda f: f"{f:.0f}")

    assert list(sorted(differences.in_both)) == [3, 4]
    assert list(sorted(differences.in_first)) == [1, 2]
    assert list(sorted(differences.in_second)) == [5.0, 6.0]

    differences = find_differences(group2, lambda f: f"{f:.0f}", group1, lambda i: f"{i:d}")

    assert list(sorted(differences.in_both)) == [3.0, 4.0]
    assert list(sorted(differences.in_first)) == [5.0, 6.0]
    assert list(sorted(differences.in_second)) == [1, 2]