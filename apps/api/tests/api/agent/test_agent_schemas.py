from app.schemas.agent import ChatRequest


def test_chat_request_accepts_timezone():
    req = ChatRequest(message="hi", user_id="u1", timezone="Asia/Ho_Chi_Minh")
    assert req.timezone == "Asia/Ho_Chi_Minh"


def test_chat_request_timezone_optional():
    assert ChatRequest(message="hi", user_id="u1").timezone is None


def test_chat_request_bad_timezone_still_parses():
    # Router validates + falls back; schema must not 422 on a bad tz string.
    assert (
        ChatRequest(message="hi", user_id="u1", timezone="Not/AZone").timezone
        == "Not/AZone"
    )
