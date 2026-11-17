from repositories.sqlserver_missing_repository import compare_dict_lists


def test_partial_shortage_keeps_name_paired_with_representative_id():
    current = [{"ID": "ME001", "count": 1, "name": "Current memory"}]
    original = [
        {"ID": "ME002", "count": 2, "name": "Original memory"},
        {"ID": "ME003", "count": 1, "name": "Extra memory"},
    ]

    assert compare_dict_lists(current, original) == [
        {"ID": "ME001", "count": 2, "name": "Current memory"}
    ]


def test_entirely_missing_component_uses_original_name():
    assert compare_dict_lists([], [{"ID": "CP001", "count": 1, "name": "CPU"}]) == [
        {"ID": "CP001", "count": 1, "name": "CPU"}
    ]


def test_null_name_is_returned_as_empty_string():
    assert compare_dict_lists([], [{"ID": "CP001", "count": 1, "name": None}]) == [
        {"ID": "CP001", "count": 1, "name": ""}
    ]


def test_sufficient_components_are_not_reported():
    row = {"ID": "CP001", "count": 1, "name": "CPU"}
    assert compare_dict_lists([row], [row]) == []
