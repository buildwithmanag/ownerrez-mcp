from ownerrez_mcp.store import MessageStore, parse_message_event


def test_add_list_and_mark_handled(tmp_path):
    store = MessageStore(str(tmp_path / "m.db"))
    eid = store.add_event(
        {"category": "message", "thread_id": 55, "guest": "Ada", "body": "Hi", "is_incoming": True}
    )
    open_ = store.list_open()
    assert len(open_) == 1
    assert open_[0]["id"] == eid
    assert open_[0]["thread_id"] == "55"

    assert store.mark_handled(eid) is True
    assert store.list_open() == []
    assert store.counts() == {"total": 1, "open": 0}


def test_outbound_not_listed_as_open(tmp_path):
    store = MessageStore(str(tmp_path / "m.db"))
    store.add_event({"category": "message", "is_incoming": False, "body": "sent"})
    assert store.list_open() == []


def test_parse_message_event_extracts_fields():
    payload = {
        "action": "created",
        "category": "message",
        "entity": {
            "threadId": 8891,
            "booking_id": 42,
            "body": "Can I check in early?",
            "direction": "inbound",
            "guest": {"first_name": "Grace", "last_name": "Hopper"},
        },
    }
    event = parse_message_event(payload)
    assert event["category"] == "message"
    assert event["thread_id"] == 8891
    assert event["booking_id"] == 42
    assert event["guest"] == "Grace Hopper"
    assert event["is_incoming"] is True
    assert event["body"] == "Can I check in early?"
    assert event["raw"] == payload
