from tg_harness import telegram


def test_chunks_split_long_text_and_never_return_empty():
    assert telegram.chunks("a" * 8001) == ["a" * 4000, "a" * 4000, "a"]
    assert telegram.chunks("") == ["(empty)"]


def test_typing_sends_status_immediately(sent):
    with telegram.typing(1):
        pass
    assert sent == [("sendChatAction", {"chat_id": 1, "action": "typing"})]
