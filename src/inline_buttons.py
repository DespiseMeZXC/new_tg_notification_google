import json
from aiogram.types import InlineKeyboardButton


class StatisticsCallbackFactory:
    week_button = InlineKeyboardButton(
        text="За неделю", callback_data=json.dumps({"t": "statistics", "d": "week"})
    )
    month_button = InlineKeyboardButton(
        text="За месяц", callback_data=json.dumps({"t": "statistics", "d": "month"})
    )
    year_button = InlineKeyboardButton(
        text="За год", callback_data=json.dumps({"t": "statistics", "d": "year"})
    )

    def get_buttons(self):
        return [[self.week_button, self.month_button], [self.year_button]]


class FeedbackCallbackFactory:
    def __init__(self, message_id: int):
        self.message_id = message_id
        self.rating_1_button = InlineKeyboardButton(
            text="⭐",
            callback_data=json.dumps({"t": "f", "d": "1", "m": self.message_id}),
        )
        self.rating_2_button = InlineKeyboardButton(
            text="⭐⭐",
            callback_data=json.dumps({"t": "f", "d": "2", "m": self.message_id}),
        )
        self.rating_3_button = InlineKeyboardButton(
            text="⭐⭐⭐",
            callback_data=json.dumps({"t": "f", "d": "3", "m": self.message_id}),
        )
        self.rating_4_button = InlineKeyboardButton(
            text="⭐⭐⭐⭐",
            callback_data=json.dumps({"t": "f", "d": "4", "m": self.message_id}),
        )
        self.rating_5_button = InlineKeyboardButton(
            text="⭐⭐⭐⭐⭐",
            callback_data=json.dumps({"t": "f", "d": "5", "m": self.message_id}),
        )

    def get_feedback_buttons(self):
        return [
            [
                self.rating_1_button,
                self.rating_2_button,
                self.rating_3_button,
            ],
            [self.rating_4_button, self.rating_5_button],
        ]
