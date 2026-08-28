import pytest

from app.agent.action_parser import ActionParseError, extract_json_object, parse_agent_action


def test_extract_json_object_from_wrapped_text() -> None:
    raw = 'prefix {"kind":"final","final_report":"done"} suffix'
    assert extract_json_object(raw) == '{"kind":"final","final_report":"done"}'


def test_parse_agent_action_validates_shape() -> None:
    action = parse_agent_action('{"kind":"plan","plan":[{"id":"a","title":"A"}]}')
    assert action.kind == "plan"
    assert action.plan[0].id == "a"


def test_parse_agent_action_rejects_non_json() -> None:
    with pytest.raises(ActionParseError):
        parse_agent_action("not json")

