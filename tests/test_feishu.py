from sequoia_x.notify.feishu import FeishuNotifier

def test_notifier_init():
    from sequoia_x.core.config import Settings
    s = Settings(tickflow_api_key="test")
    n = FeishuNotifier(s)
    assert n.settings == s
