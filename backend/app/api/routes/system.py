from fastapi import APIRouter

from app.analytics.classifier import CLASSES, get_classifier
from app.analytics.intelligence import ENGINE_VERSION, WEIGHTS
from app.config import get_settings
from app.core.responses import ok
from app.health.service import system_health
from app.notifications.service import channel_status

router = APIRouter(tags=["System"])


@router.get("/system/health", summary="Component health (connected / degraded / unavailable)")
def get_system_health():
    """API, database, NASA FIRMS, industrial data, land cover, real-time stream, notification
    service and scheduler - each from a live check or the latest recorded run."""
    return ok(system_health())


@router.get("/notifications/channels", summary="Notification channel status")
def get_channels():
    """Which channels are configured (no credentials are ever returned) and their last delivery."""
    return ok(channel_status())


@router.get("/intelligence/model", summary="Intelligence engine and classifier in use")
def get_model():
    """States plainly which classifier is active. Today: a transparent rule-based baseline - no
    trained model is claimed because no validated, labelled training set exists yet."""
    clf = get_classifier(get_settings().classifier)
    return ok(
        {
            "engine_version": ENGINE_VERSION,
            "classifier": {"name": clf.name, "version": clf.version, "kind": clf.kind, "trained_model": clf.trained},
            "classes": CLASSES,
            "factor_weights": WEIGHTS,
            "note": "Rule-based, feature-driven baseline. A trained model can replace it through the same "
                    "Classifier interface once validated labels exist (see ml/export_features.py).",
        }
    )
