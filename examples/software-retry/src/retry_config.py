"""小范围真实功能示例：校验重试次数。"""


def validate_retry_count(value):
    if type(value) is not int:
        raise TypeError("retry count must be an integer")
    if value < 0:
        raise ValueError("retry count must be non-negative")
    return value
