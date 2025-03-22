# Workaround to force unittest to print out all diffs without truncation
# https://stackoverflow.com/a/61345284
__import__('sys').modules['unittest.util']._MAX_LENGTH = 999999999