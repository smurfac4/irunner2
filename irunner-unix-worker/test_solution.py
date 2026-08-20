from pathlib import Path


def test_cpp_has_class():
    # Search for the C++ solution file in the temporary directory
    solution_path = Path('solution.cpp')

    # If there is no such file, try to find another solution file
    if not solution_path.exists():
        # In case the worker saves it under a different name
        files = list(Path('.').glob('*.cpp'))
        if files:
            solution_path = files[0]

    assert solution_path.exists(), "The C++ solution file was not found!"

    # Read the text of the student's code
    code_text = solution_path.read_text(encoding='utf-8', errors='replace')

    # Check if the word "class" is present in the code
    assert 'class' in code_text, "The 'class' keyword must be used in the student's code!"