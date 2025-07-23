from prometheus_client import Counter, Histogram


def prom_counter(name: str, desc: str) -> Counter:
    """Return a Prometheus Counter."""
    return Counter(name, desc)


def prom_hist(name: str, desc: str) -> Histogram:
    """Return a Prometheus Histogram."""
    return Histogram(name, desc)

