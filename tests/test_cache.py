from agents.cache import cached_locality_lookup, clear_locality_cache


def test_cached_locality_lookup_calls_compute_fn_once_per_key():
    clear_locality_cache()
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return f"result-{calls['n']}"

    first = cached_locality_lookup("Whitefield", compute)
    second = cached_locality_lookup("Whitefield", compute)

    assert first == "result-1"
    assert second == "result-1"
    assert calls["n"] == 1


def test_cached_locality_lookup_different_keys_both_compute():
    clear_locality_cache()
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return calls["n"]

    a = cached_locality_lookup("Koramangala", compute)
    b = cached_locality_lookup("Indiranagar", compute)

    assert a == 1
    assert b == 2
    assert calls["n"] == 2


def test_clear_locality_cache_resets_state():
    clear_locality_cache()
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return calls["n"]

    cached_locality_lookup("HSR Layout", compute)
    clear_locality_cache()
    cached_locality_lookup("HSR Layout", compute)

    assert calls["n"] == 2
