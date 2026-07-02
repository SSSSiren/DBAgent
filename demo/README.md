# utils.py

Utility functions for the SDK-DBAgent project.

## Functions

### `calculate_average(numbers)`

Calculates the arithmetic mean of a list of numbers.

**Parameters:**

| Name      | Type              | Description                  |
|-----------|-------------------|------------------------------|
| `numbers` | `list[int | float]` | A non-empty list of numeric values. |

**Returns:** `float` — The arithmetic mean of the input numbers.

**Raises:**

| Exception     | Condition                              |
|---------------|----------------------------------------|
| `ValueError`  | The `numbers` list is empty.           |

**Example:**

```python
>>> calculate_average([1, 2, 3, 4, 5])
3.0
```

---

### `get_user_name(user)`

Extracts and uppercases the `name` field from a user dictionary.

**Parameters:**

| Name   | Type   | Description                                     |
|--------|--------|-------------------------------------------------|
| `user` | `dict` | A dictionary that must contain a non-`None` `"name"` key. |

**Returns:** `str` — The user's name converted to uppercase.

**Raises:**

| Exception    | Condition                                                    |
|--------------|--------------------------------------------------------------|
| `TypeError`  | `user` is not a `dict`.                                      |
| `KeyError`   | `user` dict is missing the `"name"` key, or its value is `None`. |

**Example:**

```python
>>> get_user_name({"name": "alice"})
'ALICE'
```