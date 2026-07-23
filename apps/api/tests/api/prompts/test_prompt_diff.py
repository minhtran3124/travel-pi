from app.core.prompt_diff import build_line_diff


def test_identical_input_is_all_context():
    text = "a\nb\nc"
    result = build_line_diff(text, text)

    assert all(row.tag == "context" for row in result["unified"])
    assert not any(row.tag in ("add", "del") for row in result["unified"])
    assert len(result["left"]) == len(result["right"])


def test_pure_insertion_adds_only_and_pads_left():
    result = build_line_diff("", "x\ny")

    assert all(row.tag == "add" for row in result["unified"])
    assert [row.text for row in result["unified"]] == ["x", "y"]
    assert result["left"] == [None, None]
    assert [row.text for row in result["right"]] == ["x", "y"]


def test_pure_deletion_dels_only_and_pads_right():
    result = build_line_diff("x\ny", "")

    assert all(row.tag == "del" for row in result["unified"])
    assert [row.text for row in result["unified"]] == ["x", "y"]
    assert result["right"] == [None, None]
    assert [row.text for row in result["left"]] == ["x", "y"]


def test_replace_yields_context_then_del_then_add():
    result = build_line_diff("a\nb", "a\nc")

    unified = result["unified"]
    assert [(row.tag, row.text) for row in unified] == [
        ("context", "a"),
        ("del", "b"),
        ("add", "c"),
    ]

    context_row, del_row, add_row = unified
    assert context_row.old_no == 1 and context_row.new_no == 1
    assert del_row.old_no == 2 and del_row.new_no is None
    assert add_row.old_no is None and add_row.new_no == 2


def test_left_right_alignment_invariant_holds_for_mixed_diff():
    old = "a\nb\nc\nd"
    new = "a\nx\nc\ny\nz"
    result = build_line_diff(old, new)

    assert len(result["left"]) == len(result["right"])
