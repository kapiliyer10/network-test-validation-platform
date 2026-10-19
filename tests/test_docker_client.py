from unittest.mock import MagicMock, patch

import pytest

from src.docker_client import get_container

pytestmark = pytest.mark.unit


@patch("src.docker_client.docker.from_env")
def test_get_running_container(mock_from_env):
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.status = "running"

    mock_client.containers.get.return_value = mock_container
    mock_from_env.return_value = mock_client

    result = get_container("clab-srl-lab-R1")

    mock_client.containers.get.assert_called_once_with("clab-srl-lab-R1")
    assert result is mock_container


@patch("src.docker_client.docker.from_env")
def test_get_container_rejects_stopped_container(mock_from_env):
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.status = "exited"

    mock_client.containers.get.return_value = mock_container
    mock_from_env.return_value = mock_client

    with pytest.raises(RuntimeError, match="Container is not running"):
        get_container("clab-srl-lab-R1")
