from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field, model_validator


class ActionBase(BaseModel):
    """Base class for all actions."""

    @computed_field  # type: ignore
    @property
    def action_type(self) -> str:
        """The type of action, computed from the class name."""
        return self._get_action_type()

    @staticmethod
    def _get_action_type() -> str:
        """Get the action type for this action class."""
        raise NotImplementedError("Subclasses must implement _get_action_type")


class SetSlotAction(ActionBase):
    """Action to set a slot value."""

    flow_name: str = Field(..., description="The name of the flow ('global' for global slots)")
    slot_name: str = Field(..., description="The name of the slot to set")
    slot_value: bool | int | float | str = Field(..., description="The value to set for the slot")

    @model_validator(mode="after")
    def validate_flow_name_and_slots(self) -> "SetSlotAction":
        """Validate that flow_name is legitimate and slot_name exists in the appropriate flow."""
        from carriage_services.conversation.flows import FLOW_REGISTRY, Flow

        legitimate_flow_names = set(FLOW_REGISTRY.keys()) | {"global"}
        if self.flow_name not in legitimate_flow_names:
            raise ValueError(
                f"Invalid flow_name '{self.flow_name}'. Must be one of: {', '.join(sorted(legitimate_flow_names))}"
            )

        if self.flow_name == "global":
            global_slots = Flow.get_global_slots()
            if self.slot_name not in global_slots:
                available_slots = list(global_slots.keys())
                raise ValueError(
                    f"Invalid slot_name '{self.slot_name}' for global flow. "
                    f"Available global slots: {', '.join(available_slots)}"
                )
        else:
            flow_instance = FLOW_REGISTRY[self.flow_name]
            local_slots = flow_instance.local_slots
            if self.slot_name not in local_slots:
                available_slots = list(local_slots.keys())
                raise ValueError(
                    f"Invalid slot_name '{self.slot_name}' for flow '{self.flow_name}'. "
                    f"Available local slots: {', '.join(available_slots)}"
                )

        return self

    @staticmethod
    def _get_action_type() -> str:
        return "set_slot"


class StartFlowAction(ActionBase):
    """Action to start a new flow."""

    flow_name: str = Field(..., description="The name of the flow to start")

    @model_validator(mode="after")
    def validate_flow_name(self) -> "StartFlowAction":
        """Validate that flow_name is a legitimate flow that can be started."""
        from carriage_services.conversation.flows import FLOW_REGISTRY

        legitimate_flow_names = set(FLOW_REGISTRY.keys())
        if self.flow_name not in legitimate_flow_names:
            raise ValueError(
                f"Invalid flow_name '{self.flow_name}'. Must be one of: {', '.join(sorted(legitimate_flow_names))}"
            )

        return self

    @staticmethod
    def _get_action_type() -> str:
        return "start_flow"


class CancelFlowAction(ActionBase):
    """Action to cancel the current flow."""

    @staticmethod
    def _get_action_type() -> str:
        return "cancel_flow"


class ContinueAction(ActionBase):
    """Action to continue the current flow without changing any slots."""

    # This field is necessary because without it intent classification model always generates an incorrect action
    # instead of ContinueAction because they contain additional fields and are preferred by the model
    user_message: str = Field(..., description="Just continue the flow without changing any slots")

    @staticmethod
    def _get_action_type() -> str:
        return "continue_flow"


class RepetitionAction(ActionBase):
    """Action to repeat the last message when the last user response was not understood."""

    # This field is necessary because without it intent classification model always generates an incorrect SetSlotAction
    # instead of RepetitionAction because it contains additional fields so is more detailed and preferred by the model
    user_message: str = Field(..., description="The user's message that was not understood")

    @staticmethod
    def _get_action_type() -> str:
        return "repetition"


class Action(BaseModel):
    """
    Base class for all actions performed by the agent.
    """

    action: SetSlotAction | StartFlowAction | ContinueAction | RepetitionAction = Field(
        ..., description="Action to perform"
    )


class RegularFlowAction(Action):
    """
    Actions allowed in regular flows (non-booking flows).
    All action types are permitted.
    """

    action: SetSlotAction | StartFlowAction | RepetitionAction = Field(
        ..., description="Action to perform in regular flow"
    )


class BookingFlowAction(Action):
    """
    A booking flow specific action performed by the agent.
    Only certain actions are allowed during booking flow.
    """

    action: SetSlotAction | StartFlowAction | ContinueAction | RepetitionAction = Field(
        ..., description="Action to perform during booking flow"
    )


class Slot(BaseModel):
    """Represents a slot that can be collected in a flow."""

    name: str
    description: str
    value: Any
    allowed_values: list[str] | None = None
    type: str | None = None
    required_slots: list[tuple[str, Any]] | None = None


class BookingFlowMessage(BaseModel):
    """Response message from the booking flow with appointment selection status."""

    booking_response_message: str = Field(
        ..., description="The response message to send to the user during the booking process"
    )
    appointment_datetime: datetime | None = Field(
        default=None,
        description=(
            "The appointment datetime that the user has EXPLICITLY CONFIRMED. "
            "ONLY fill this field when the user has clearly and directly confirmed the appointment time "
            "(e.g., 'yes', 'that works', 'confirmed', 'book it', 'yes please'). "
            "DO NOT fill this field if: the user is just asking about availability, considering options, "
            "or has not yet given explicit confirmation. Leave as None until confirmation is received."
        ),
    )
    user_said_goodbye: bool = Field(
        default=False,
        description=(
            "Whether the user has indicated they want to end the conversation. "
            "Set to True when user says goodbye, thanks and ends conversation, indicates they're done, "
            "or says phrases like: 'goodbye', 'bye', 'thank you goodbye', 'that's all', 'that's it', "
            "'thanks that's all', 'I'm good', 'that's everything', 'nothing else', 'have a nice day', "
            "'talk to you later', 'I have to go', 'gotta go', or similar farewell/ending phrases."
        ),
    )
