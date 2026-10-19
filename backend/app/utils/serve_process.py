import os


def should_start_background_services():
    """Debug reloader 的父进程也会执行 create_app。

    父进程若再连 MQTT、跑定时写库，会和真正对外服务的子进程抢同一份 SQLite。
    """
    if os.environ.get('SJIC_RELOADER') == '1' and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return False
    return True
