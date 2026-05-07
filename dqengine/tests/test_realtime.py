"""实时流式验证测试."""

import json
import tempfile
from pathlib import Path

import pytest

from dqengine.realtime.validator import StreamValidator


class TestStreamValidator:
    """流式验证器测试."""

    @pytest.fixture
    def stream_json(self):
        data = [
            {"id": "evt_1", "data": {"name": "Test", "age": 30, "email": "test@example.com"}},
            {"id": "evt_2", "data": {"name": "User", "age": 25, "email": "user@example.com"}},
            {"id": "evt_3", "data": {"name": "", "age": -1, "email": "bad"}},
            {"id": "evt_4", "data": {"name": "Admin", "age": 40, "email": "admin@test.org"}},
            {"id": "evt_5", "data": {"name": "Guest", "age": 22, "email": "guest@mail.com"}},
        ]
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(data, f)
            return f.name

    def test_local_stream_basic(self, stream_json):
        validator = StreamValidator(mode="local")
        results = list(validator.validate_stream(stream_json))
        assert len(results) == 5

    def test_local_stream_with_max_events(self, stream_json):
        validator = StreamValidator(mode="local")
        results = list(validator.validate_stream(stream_json, max_events=2))
        assert len(results) == 2

    def test_local_stream_all_passed_no_rules(self, stream_json):
        validator = StreamValidator(mode="local")  # 无规则=全部通过
        results = list(validator.validate_stream(stream_json))
        assert all(r.passed for r in results)

    def test_file_not_found(self):
        validator = StreamValidator(mode="local")
        with pytest.raises(FileNotFoundError):
            list(validator.validate_stream("nonexistent.json"))

    def test_invalid_mode(self):
        validator = StreamValidator(mode="invalid")
        with pytest.raises(ValueError, match="不支持的流模式"):
            list(validator.validate_stream("dummy.json"))

    def test_websocket_not_implemented(self):
        validator = StreamValidator(mode="websocket")
        with pytest.raises(NotImplementedError):
            list(validator._validate_websocket_stream("ws://localhost"))

    def test_kafka_not_implemented(self):
        validator = StreamValidator(mode="kafka")
        with pytest.raises(NotImplementedError):
            list(validator._validate_kafka_stream("topic"))

    def test_single_event_dict_handling(self):
        data = {"id": "single", "data": {"col": "value"}}
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(data, f)
            f_path = f.name

        try:
            validator = StreamValidator(mode="local")
            results = list(validator.validate_stream(f_path))
            assert len(results) == 1
            assert results[0].event_id == "single"
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_batch_stream_validation(self):
        import pandas as pd

        df = pd.DataFrame({
            "name": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
            "age": [25, 30, 35, 40, 45, 50, 55, 60, 65, 70],
        })

        validator = StreamValidator(mode="local")
        results = list(validator.validate_batch_stream(df, "configs/rules.yaml", chunk_size=3))
        # 10 rows, chunk_size 3 => 4 chunks
        assert len(results) == 4
