from sequoia_x.core.logger import get_logger

def test_logger():
    logger = get_logger("test")
    assert logger.name == "test"
