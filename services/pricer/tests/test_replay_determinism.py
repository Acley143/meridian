"""The property the last three sessions were built to make possible: the
same fixture, run twice, produces byte-identical snapshots except
`ingest_time`."""
import dataclasses

from pricer_test_helpers import run_fixture_pipeline


def _strip_ingest_time(snapshots):
    return sorted(
        (dataclasses.replace(s, ingest_time=None) for s in snapshots),
        key=lambda s: (s.portfolio_id, s.as_of),
    )


def test_replay_is_byte_identical_except_ingest_time(kafka_stack) -> None:
    run_a = run_fixture_pipeline(kafka_stack)
    run_b = run_fixture_pipeline(kafka_stack)

    assert len(run_a) == 4
    assert len(run_b) == 4
    assert _strip_ingest_time(run_a) == _strip_ingest_time(run_b)

    ingest_times_a = sorted(s.ingest_time for s in run_a)
    ingest_times_b = sorted(s.ingest_time for s in run_b)
    assert ingest_times_a != ingest_times_b, (
        "ingest_time was identical across two separate runs -- suspiciously "
        "unlikely unless ingest_time isn't actually being stamped fresh"
    )
