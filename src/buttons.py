from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


class KeyboardAccount:
    def __init__(self):
        self.keyboard_account = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🔐 Аккаунты Google")],
                [KeyboardButton(text="🔐 Добавить аккаунт")],
                [KeyboardButton(text="🔐 Удалить аккаунт")],
            ],
            resize_keyboard=True,
        one_time_keyboard=False
    )


class KeyboardAccountsList:
    def __init__(self):
        self.keyboard = []
        
    def get_keyboard_accounts_list(self, email: list):
        
        for i in email:
            self.keyboard.append([KeyboardButton(text=i)])
        self.keyboard.append([KeyboardButton(text="🔐 Аккаунты Google")])
        self.keyboard.append([KeyboardButton(text="🔐 Добавить аккаунт")])
        self.keyboard.append([KeyboardButton(text="🔐 Удалить аккаунт")])
        return ReplyKeyboardMarkup(
            keyboard=self.keyboard,
            resize_keyboard=True,
            one_time_keyboard=False
        )


class KeyboardAccountActions:
    def __init__(self):
        self.keyboard = []
        
    def get_keyboard_account_actions(self):
        self.keyboard.append([KeyboardButton(text="🔐 Удалить аккаунт")])
        self.keyboard.append([KeyboardButton(text="🔐 Добавить аккаунт")])
        self.keyboard.append([KeyboardButton(text="🔐 Аккаунты Google")])
        return ReplyKeyboardMarkup(
            keyboard=self.keyboard,
            resize_keyboard=True,
            one_time_keyboard=False
        )
