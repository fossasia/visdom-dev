# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""One number box per plan limit, in place of a JSON textarea.

A plan's limits are stored as one JSON object, which is right for the data and
wrong for a person typing it: a missing quote or a misspelt key is easy to make
and hard to spot. The form shows a box for each limit instead. An empty box
means unlimited, and what comes out the other side is the same object the rest
of the code already checks and saves.
"""

import wtforms
from markupsafe import Markup, escape
from wtforms.utils import unset_value

from app import billing

LABELS = {
    "workspaces": "Workspaces",
    "members": "Team members",
    "api_keys": "API keys",
    "storage_mb": "Storage, all workspaces (MB)",
    "workspace_storage_mb": "Storage, one workspace (MB)",
}


class LimitBoxes:
    """Draws the boxes, filled with what was typed or with the saved limits."""

    def __call__(self, field, **kwargs):
        saved = field.data if isinstance(field.data, dict) else {}
        invalid = " is-invalid" if "is-invalid" in str(kwargs.get("class", "")) else ""
        boxes = []
        for key in billing.LIMIT_KEYS:
            if field.typed is not None:
                shown = field.typed.get(key, "")
            else:
                value = saved.get(key)
                shown = "" if value is None else str(value)
            boxes.append(
                '<label class="ap-limit">'
                f'<span class="ap-limit-name">{escape(LABELS.get(key, key))}</span>'
                f'<input class="form-control" type="number" min="0" step="1" inputmode="numeric" '
                f'name="{escape(field.name)}-{escape(key)}" value="{escape(shown)}" placeholder="Unlimited">'
                "</label>"
            )
        return Markup(f'<div class="ap-limits{invalid}">{"".join(boxes)}</div>')


class LimitsField(wtforms.Field):
    """A plan's limits as a dict, read from one input per limit."""

    widget = LimitBoxes()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.typed = None

    def process(self, formdata, data=unset_value, extra_filters=None):
        super().process(None, data, extra_filters)
        self.typed = None
        if formdata is None:
            return

        names = {key: f"{self.name}-{key}" for key in billing.LIMIT_KEYS}
        if any(name not in formdata for name in names.values()):
            self.raw_data = []
            self.process_errors.append("Every limit must be sent, even when it is left empty.")
            return

        typed, limits, problems = {}, {}, []
        for key, name in names.items():
            raw = (formdata.getlist(name)[0] or "").strip()
            typed[key] = raw
            if raw == "":
                limits[key] = None
            elif raw.isascii() and raw.isdigit():
                limits[key] = int(raw)
            else:
                problems.append(
                    f"{LABELS.get(key, key)} must be a whole number of zero or more, or empty for unlimited."
                )
        self.typed = typed
        self.raw_data = [typed]
        if problems:
            self.process_errors.extend(problems)
        else:
            self.data = limits


class FeatureLines(wtforms.TextAreaField):
    """A plan's feature bullets as a list, typed one to a line."""

    def _value(self):
        if self.raw_data:
            return self.raw_data[0]
        return "\n".join(self.data or [])

    def process_formdata(self, valuelist):
        if valuelist:
            self.data = [line.strip() for line in valuelist[0].splitlines() if line.strip()]

