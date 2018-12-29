# How to develop Lark - Guide

There are many ways you can help the project:

* Help solve issues
* Improve the documentation
* Write new grammars for Lark's library
* Write a blog post introducing Lark to your audience
* Port Lark to another language
* Help me with code developemnt

If you're interested in taking one of these on, let me know and I will provide more details and assist you in the process.


## Unit Tests

If you would like to run all Unit Tests,
all you need is a supported Python Interpreter.
You can consult the list of supported interpreter for unit testing on the `tox.ini` file.
Then, just run the command `python -m tests`

If you would like to run a single Unit Test,
you do not need to use tox,
you can directly run it with your installed Python Interpreter.
First you need to figure out what is the test full name.
For example:
```python
##   test_package test_class_name.test_function_name
python -m tests TestLalrStandard.test_lexer_error_recovering
```

Equivalent example/way, but unrecommended:
```python
##          test_package.tests_module.test_class_name.test_function_name
python -m unittest tests.test_parser.TestLalrStandard.test_lexer_error_recovering
```

### tox

To run all Unit Tests with tox,
install tox and Python 2.7 up to the latest python interpreter supported (consult the file tox.ini).
Then,
run the command `tox` on the root of this project (where the main setup.py file is on).

And, for example,
if you would like to only run the Unit Tests for Python version 2.7,
you can run the command `tox -e py27`
