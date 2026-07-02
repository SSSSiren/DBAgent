def calculate_average(numbers):
    if not numbers:
        raise ValueError("numbers must not be empty")
    total = 0
    for num in numbers:
        total += num
    return total / len(numbers)


def get_user_name(user):
    if not isinstance(user, dict):
        raise TypeError("user must be a dict")
    name = user.get("name")
    if name is None:
        raise KeyError("user dict must contain a non-None 'name' key")
    return name.upper()