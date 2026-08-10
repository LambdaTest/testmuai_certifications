"""Context available to every template."""

from django.urls import reverse

MAIN_SITE = "https://www.testmuai.com"

#: Header navigation. The first four point at the main TestMu AI site — confirm
#: the real paths before this ships. Only Certifications lives in this app.
NAV_ITEMS = [
    {"key": "platform", "label": "Platform", "url": f"{MAIN_SITE}/platform/"},
    {"key": "ai-agents", "label": "AI Agents", "url": f"{MAIN_SITE}/ai-agents/"},
    {"key": "resources", "label": "Resources", "url": f"{MAIN_SITE}/resources/"},
    {"key": "certifications", "label": "Certifications", "url": None},
]


def navigation(request):
    items = []
    for item in NAV_ITEMS:
        item = dict(item)
        if item["url"] is None:
            item["url"] = reverse("exam:book")
        items.append(item)

    # Every page in this app sits under Certifications. Override per view by
    # setting `nav_active` in the context.
    return {"nav_items": items, "nav_active": "certifications"}
