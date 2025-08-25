"""
Backfill für 'decrbyfloat' in redis-py:
Redis kennt kein DECRBYFLOAT; korrekt ist INCRBYFLOAT mit negativem Wert.
Manche Codepfade rufen jedoch 'decrbyfloat' auf. Dieses Modul ergänzt die Methode
auf Redis/StrictRedis/Pipeline, falls sie fehlt.
"""
from __future__ import annotations
from typing import Any

def ensure_redis_decrbyfloat() -> None:
    try:
        from redis.client import Redis, StrictRedis, Pipeline  # type: ignore
    except Exception:
        # redis nicht installiert: nichts zu tun
        return

    def _impl(self: Any, name: str, amount: float = 1.0) -> float:
        """
        Dekrementiert einen Float-Wert durch INCRBYFLOAT mit negativem Betrag.
        Gibt den neuen Wert als float zurück (wie incrbyfloat).
        """
        try:
            amt = float(amount)
        except Exception:
            amt = 0.0
        # redis-py gibt float als Python-Float zurück
        return self.incrbyfloat(name, -amt)  # type: ignore[attr-defined]

    for cls in _iter_target_classes():
        if not hasattr(cls, "decrbyfloat"):
            try:
                setattr(cls, "decrbyfloat", _impl)
            except Exception:
                # Im Zweifel lieber still weiterlaufen als Import zu blockieren
                pass

def _iter_target_classes():
    """Hilfsfunktion: liefert Redis, StrictRedis, Pipeline falls vorhanden."""
    try:
        from redis.client import Redis, StrictRedis, Pipeline  # type: ignore
        yield Redis
        yield StrictRedis
        yield Pipeline
    except Exception:
        return

# Bei Modulimport direkt aktivieren (idempotent)
try:
    ensure_redis_decrbyfloat()
except Exception:
    pass
