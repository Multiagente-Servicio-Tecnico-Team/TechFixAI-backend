from langchain_core.messages import AIMessage

from tests.contract.patterns.conftest import FakeModel


def test_fake_model_supports_tool_and_structured_output_contracts():
    model = FakeModel([AIMessage(content="fixture")])
    model.bind_tools([object()], tool_choice="auto")
    model.with_structured_output(dict, method="json_mode")

    assert model.invoke(["input"]).content == "fixture"
    assert model.bound_tools[0][1]["tool_choice"] == "auto"
    assert model.structured_schemas[0][0] is dict
