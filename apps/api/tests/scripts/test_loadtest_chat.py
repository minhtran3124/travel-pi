"""gh-293: the concurrent-chat load script runs keyless and flags state cross-talk."""

import asyncio

from scripts import loadtest_chat as lt


def _run(tmp_path, concurrency):
    url = f"sqlite:///{tmp_path / 'load.db'}"

    async def go():
        async with lt._fake_app(url) as app:
            return await lt.run_level(app, concurrency, 2, None)

    return asyncio.run(go())


def test_five_concurrent_chats_pass_on_fake_llm(tmp_path):
    res = _run(tmp_path, 5)
    assert res.requests == 10
    assert res.status_5xx == 0 and res.exceptions == 0
    assert res.crosstalk_violations == 0
    assert res.passed


def test_history_check_flags_foreign_and_missing_tokens():
    class _Client:
        async def get(self, *a, **kw):
            class R:
                status_code = 200

                @staticmethod
                def json():
                    return {
                        "messages": [
                            {"content": "tokabcx1x0"},
                            {"content": "ack:tokabcx9x9"},
                        ]
                    }

            return R()

    # Own tokabcx1x0 present, foreign tokabcx9x9 present, own tokabcx1x1 missing.
    bad = asyncio.run(
        lt._verify_history(_Client(), "u", "c", ["tokabcx1x0", "tokabcx1x1"], "abc")
    )
    assert bad == 2


def test_verdict_gates_on_5xx_and_connection_budget():
    res = lt._finish(lt.Result(concurrency=10, turns_per_chat=1), [0.1] * 19 + [2.0])
    assert res.passed
    res.status_5xx = 1
    assert not lt._finish(res, [0.1]).passed
    over = lt.Result(
        concurrency=10, turns_per_chat=1, peak_connections=71, max_connections=100
    )
    assert not lt._finish(over, [0.1]).passed
