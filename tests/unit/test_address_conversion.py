"""Test the address number conversion functionality."""

from carriage_services.utils.helpers import convert_numbers_to_string_digits


def test_converts_address_numbers() -> None:
    """Test that numbers in addresses are converted to spoken digits."""
    data = {"funeral_home_address": "2052 Howard Road Camarillo, California"}

    result = convert_numbers_to_string_digits(data)

    expected = "two zero five two Howard Road Camarillo, California"
    assert result["funeral_home_address"] == expected


def test_converts_full_lead_data_example() -> None:
    """Test conversion with the actual lead data structure."""
    data = {
        "lead_id": "8d806ae8-b839-4565-9b19-587a3b9825db",
        "user_name": "Mateusz Wosiński",
        "email": None,
        "calendar_id": "1842fae0-9880-f011-b4cc-002248a1e81f",
        "phone": None,
        "interest_level": None,
        "source": "dynamics_crm",
        "funeral_home_name": "Bradshaw Carter Funeral Home",
        "funeral_home_address": "2052 Howard Road Camarillo, California",
    }

    result = convert_numbers_to_string_digits(data)

    # The main test: address numbers are converted
    assert result["funeral_home_address"] == "two zero five two Howard Road Camarillo, California"

    # Other fields remain as expected
    assert result["user_name"] == "Mateusz Wosiński"
    assert result["email"] is None
    assert result["phone"] is None
    assert result["source"] == "dynamics_crm"
    assert result["funeral_home_name"] == "Bradshaw Carter Funeral Home"

    # UUIDs should remain unchanged (not converted)
    assert result["lead_id"] == data["lead_id"]
    assert result["calendar_id"] == data["calendar_id"]


def test_preserves_text_without_numbers() -> None:
    """Test that text without numbers remains unchanged."""
    data = {"name": "Bradshaw Carter Funeral Home", "city": "Camarillo", "state": "California"}

    result = convert_numbers_to_string_digits(data)

    assert result == data  # Should be identical


def test_preserves_uuids() -> None:
    """Test that UUID strings are not converted."""
    data = {
        "uuid1": "8d806ae8-b839-4565-9b19-587a3b9825db",
        "uuid2": "1842fae0-9880-f011-b4cc-002248a1e81f",
        "address": "123 Main St",  # This should be converted
        "phone": "555-1234",  # This should be converted
    }

    result = convert_numbers_to_string_digits(data)

    # UUIDs should remain unchanged
    assert result["uuid1"] == "8d806ae8-b839-4565-9b19-587a3b9825db"
    assert result["uuid2"] == "1842fae0-9880-f011-b4cc-002248a1e81f"

    # Other strings with numbers should be converted
    assert result["address"] == "one two three Main St"
    assert result["phone"] == "five five five-one two three four"
