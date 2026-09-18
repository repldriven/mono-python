import socket

from mono_bricks.server import adapter


def _reuse_address(sock: socket.socket) -> int:
    return sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _server(sock: socket.socket) -> adapter.Server:
    # http_local_url reads only the socket.
    return adapter.Server(server=None, thread=None, socket=sock)  # type: ignore[arg-type]


def test_bind_on_port_0_leaves_reuse_address_off():
    with adapter.bind("127.0.0.1", 0) as sock:
        assert sock.getsockname()[1] > 0
        assert _reuse_address(sock) == 0


def test_bind_on_a_fixed_port_sets_reuse_address():
    port = _free_port()
    with adapter.bind("127.0.0.1", port) as sock:
        assert sock.getsockname()[1] == port
        # macOS reads the set option back as 4, not 1.
        assert _reuse_address(sock) != 0


def test_http_local_url_renders_a_wildcard_host_as_localhost():
    with adapter.bind("0.0.0.0", 0) as sock:
        port = sock.getsockname()[1]
        assert adapter.http_local_url(_server(sock)) == f"http://localhost:{port}"


def test_http_local_url_renders_a_named_host_as_given():
    with adapter.bind("127.0.0.1", 0) as sock:
        port = sock.getsockname()[1]
        assert adapter.http_local_url(_server(sock)) == f"http://127.0.0.1:{port}"
