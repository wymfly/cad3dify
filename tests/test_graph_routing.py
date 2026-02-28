"""Tests for graph conditional routing functions."""

from backend.graph.state import CadJobState


class TestRouteByInputType:
    def test_text(self) -> None:
        from backend.graph.routing import route_by_input_type
        state = CadJobState(job_id="t1", input_type="text", status="created")
        assert route_by_input_type(state) == "text"

    def test_drawing(self) -> None:
        from backend.graph.routing import route_by_input_type
        state = CadJobState(job_id="t1", input_type="drawing", status="created")
        assert route_by_input_type(state) == "drawing"

    def test_organic(self) -> None:
        from backend.graph.routing import route_by_input_type
        state = CadJobState(job_id="t1", input_type="organic", status="created")
        assert route_by_input_type(state) == "organic"


class TestRouteAfterConfirm:
    def test_text_routes_to_text(self) -> None:
        from backend.graph.routing import route_after_confirm
        state = CadJobState(job_id="t1", input_type="text", status="confirmed")
        assert route_after_confirm(state) == "text"

    def test_drawing_routes_to_drawing(self) -> None:
        from backend.graph.routing import route_after_confirm
        state = CadJobState(job_id="t1", input_type="drawing", status="confirmed")
        assert route_after_confirm(state) == "drawing"

    def test_organic_routes_to_finalize(self) -> None:
        from backend.graph.routing import route_after_confirm
        state = CadJobState(job_id="t1", input_type="organic", status="confirmed")
        assert route_after_confirm(state) == "finalize"

    def test_failed_routes_to_finalize(self) -> None:
        from backend.graph.routing import route_after_confirm
        state = CadJobState(job_id="t1", input_type="text", status="failed")
        assert route_after_confirm(state) == "finalize"
