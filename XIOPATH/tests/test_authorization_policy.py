from api.routers.ws import MAX_MESSAGE_BYTES, allowed_channels


def test_client_channels_exclude_platform_operations():
    channels = allowed_channels("client")

    assert "workers" not in channels
    assert "memory" not in channels
    assert "dlq" not in channels
    assert "analytics" not in channels


def test_admin_channels_include_operational_feeds():
    channels = allowed_channels("admin")

    assert {"workers", "memory", "dlq", "analytics"}.issubset(channels)


def test_unknown_roles_receive_least_privilege_channels():
    assert allowed_channels("forged-role") == allowed_channels("client")


def test_socket_message_limit_is_bounded():
    assert 0 < MAX_MESSAGE_BYTES <= 64 * 1024
