from prometheus_client import Counter, Histogram, REGISTRY


def prom_counter(name: str, desc: str, labels: tuple[str, ...] = ()) -> Counter:
    """Return a Prometheus Counter.

    If *labels* are provided, a labelled counter is created accordingly.
    """

    try:
        return Counter(name, desc, labels) if labels else Counter(name, desc)
    except ValueError:
        # Metric already registered - return existing collector
        return REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]


def prom_hist(name: str, desc: str) -> Histogram:
    """Return a Prometheus Histogram."""
    return Histogram(name, desc)

