# app.py
def add(a, b):
    return a + b

def test_add():
    assert add(2, 3) == 5  # Fixed back to 5!
    print("Test Passed!")

if __name__ == "__main__":
    test_add()