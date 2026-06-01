from aiogram.fsm.state import State, StatesGroup


class CreateServiceStates(StatesGroup):
    volume = State()
    expiry = State()
    client_name = State()
    confirm = State()


class ExtendExpiryStates(StatesGroup):
    add_days = State()
    set_date = State()


class EditServiceStates(StatesGroup):
    limit_ip = State()
    comment = State()


class AddTemplateStates(StatesGroup):
    volume = State()
    expiry = State()
    name = State()
    confirm = State()


class AddPanelStates(StatesGroup):
    name = State()
    base_url = State()
    api_token = State()
    sub_url = State()
    confirm = State()


class SetPanelStates(StatesGroup):
    pick_reseller = State()
    pick_panel = State()
    confirm = State()


class AddResellerStates(StatesGroup):
    telegram_id = State()
    display_name = State()
    pick_panel = State()
    quota = State()
    pick_inbounds = State()
    confirm = State()


class EditResellerStates(StatesGroup):
    value = State()
    pick_inbounds = State()
