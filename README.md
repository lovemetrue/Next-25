## Next-25 - бот для администирования грузоперевозок по РФ.
### Структура проекта:
```
├── README.md
├── __init__.py
└── app
    ├── README.md
    ├── __pycache__
    ├── config
    │   ├── __init__.py
    │   ├── __pycache__
    │   └── settings.py
    ├── database
    │   ├── Next'25.db
    │   ├── __init__.py
    │   ├── __pycache__
    │   ├── models.py
    │   ├── new_models.py
    │   └── session.py
    ├── fonts
    ├── handlers
    │   ├── __init__.py
    │   ├── __pycache__
    │   ├── attachments.py
    │   ├── chat.py
    │   ├── debug.py
    │   ├── dispatcher.py
    │   ├── driver.py
    │   ├── manager.py
    │   ├── old_dispatcher.py
    │   ├── old_driver.py
    │   ├── profile.py
    │   └── start.py
    ├── keyboards
    │   ├── __init__.py
    │   ├── __pycache__
    │   ├── filters.py
    │   ├── main_menu.py
    │   └── request_actions.py
    ├── logs
    │   ├── __init__.py
    │   ├── __pycache__
    │   ├── bot.log
    │   └── logging.py
    ├── main.py
    ├── requirements.txt
    ├── services
    │   ├── __init__.py
    │   ├── __pycache__
    │   ├── notifications.py
    │   ├── report_generator.py
    │   └── request_manager.py
    ├── states
    │   ├── __init__.py
    │   ├── __pycache__
    │   ├── request_states.py
    │   └── user_states.py
    ├── tests
    │   ├── __init__.py
    │   ├── test_handlers.py
    │   └── test_services.py
    └── utils
        ├── __init__.py
        ├── __pycache__
        ├── decorators.py
        ├── formatters.py
        ├── loader.py
        ├── set_bot_commands.py
        └── validators.py
```
