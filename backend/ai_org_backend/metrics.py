from prometheus_client import Counter, Histogram


def prom_counter(name: str, desc: str, labels: tuple[str, ...] = ()) -> Counter:
    """Return a Prometheus Counter.

    If *labels* are provided, a labelled counter is created accordingly.
    """

    return Counter(name, desc, labels) if labels else Counter(name, desc)


def prom_hist(name: str, desc: str) -> Histogram:
    """Return a Prometheus Histogram."""
    return Histogram(name, desc)

